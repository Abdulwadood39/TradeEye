from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_verified_user
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe
from backend.app.db.session import get_db
from backend.app.schemas.catalog import IndicatorResponse, TickerResponse, TimeframeResponse

router = APIRouter(tags=["catalog"])


@router.get("/tickers", response_model=list[TickerResponse])
async def list_tickers(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_verified_user),
) -> list[Ticker]:
    result = await db.execute(select(Ticker).where(Ticker.is_active.is_(True)).order_by(Ticker.display_name))
    return list(result.scalars().all())


@router.get("/timeframes", response_model=list[TimeframeResponse])
async def list_timeframes(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_verified_user),
) -> list[Timeframe]:
    result = await db.execute(select(Timeframe).where(Timeframe.is_active.is_(True)).order_by(Timeframe.code))
    return list(result.scalars().all())


@router.get("/indicators", response_model=list[IndicatorResponse])
async def list_indicators(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_verified_user),
) -> list[IndicatorType]:
    result = await db.execute(
        select(IndicatorType).where(IndicatorType.is_active.is_(True)).order_by(IndicatorType.name)
    )
    return list(result.scalars().all())
