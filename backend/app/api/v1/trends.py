from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_verified_user, is_admin_test_user
from backend.app.db.models.catalog import Ticker, Timeframe
from backend.app.db.models.scan import TrendEvent
from backend.app.db.models.user import User, UserSubscription
from backend.app.db.session import get_db
from backend.app.schemas.catalog import TrendItemResponse, TrendListResponse
from backend.app.schemas.trend_directions import visible_directions_for_user
from backend.app.services.trend_chart_service import (
    TrendChartAccessDeniedError,
    TrendChartGenerationError,
    TrendChartNotFoundError,
    build_trend_event_chart,
    prepare_trend_event_chart,
)

router = APIRouter(prefix="/trends", tags=["trends"], dependencies=[Depends(get_verified_user)])


def _safe_unlink(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@router.get("", response_model=TrendListResponse)
async def list_trends(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    ticker_id: Optional[UUID] = None,
    timeframe: Optional[str] = None,
    direction: Optional[str] = None,
    bars_scanned: Optional[int] = None,
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> TrendListResponse:
    sub_q = (
        select(
            UserSubscription.ticker_id,
            UserSubscription.timeframe_id,
            UserSubscription.bars,
        )
        .where(UserSubscription.user_id == user.id, UserSubscription.is_active.is_(True))
    )
    if ticker_id:
        sub_q = sub_q.where(UserSubscription.ticker_id == ticker_id)
    if bars_scanned:
        sub_q = sub_q.where(UserSubscription.bars == bars_scanned)

    subs = (await db.execute(sub_q)).all()
    if not subs:
        return TrendListResponse(items=[], total=0, page=page, page_size=page_size)

    conditions = []
    for ticker_id_, timeframe_id_, bars_ in subs:
        conditions.append(
            (TrendEvent.ticker_id == ticker_id_)
            & (TrendEvent.timeframe_id == timeframe_id_)
            & (TrendEvent.bars_scanned == bars_)
        )

    visible = visible_directions_for_user(is_admin_test_user=is_admin_test_user(user))
    base = select(TrendEvent).where(or_(*conditions), TrendEvent.direction.in_(visible))
    if direction:
        if direction not in visible:
            return TrendListResponse(items=[], total=0, page=page, page_size=page_size)
        base = base.where(TrendEvent.direction == direction)
    if from_:
        base = base.where(TrendEvent.scanned_at >= from_)
    if to:
        base = base.where(TrendEvent.scanned_at <= to)

    if timeframe:
        tf_result = await db.execute(select(Timeframe).where(Timeframe.code == timeframe))
        tf = tf_result.scalar_one_or_none()
        if tf:
            base = base.where(TrendEvent.timeframe_id == tf.id)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(
        base.order_by(TrendEvent.scanned_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = list(result.scalars().all())

    items = []
    for ev in events:
        ticker = (await db.execute(select(Ticker).where(Ticker.id == ev.ticker_id))).scalar_one()
        tf = (await db.execute(select(Timeframe).where(Timeframe.id == ev.timeframe_id))).scalar_one()
        items.append(
            TrendItemResponse(
                id=ev.id,
                display_name=ticker.display_name,
                yfinance_symbol=ticker.yfinance_symbol,
                timeframe=tf.code,
                direction=ev.direction,
                bars_scanned=ev.bars_scanned,
                score=ev.score,
                confidence=ev.confidence,
                scanned_at=ev.scanned_at,
            )
        )

    return TrendListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{event_id}/chart")
async def get_trend_event_chart(
    event_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        chart_input = await prepare_trend_event_chart(db, user=user, event_id=event_id)
        path = await asyncio.to_thread(build_trend_event_chart, chart_input)
    except TrendChartNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trend event not found") from exc
    except TrendChartAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not subscribed to this trend") from exc
    except TrendChartGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not generate chart",
        ) from exc

    background_tasks.add_task(_safe_unlink, path)
    return FileResponse(path, media_type="image/png", filename=f"trend_{event_id}.png")
