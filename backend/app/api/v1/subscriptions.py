from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_verified_user
from backend.app.core.config import get_settings
from backend.app.db.models.billing import Plan, Subscription
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe
from backend.app.db.models.user import User, UserSubscription
from backend.app.db.session import get_db
from backend.app.schemas.catalog import (
    SubscriptionBulkCreate,
    SubscriptionBulkResponse,
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)
from backend.app.services.billing_access import UPGRADE_REQUIRED_DETAIL, get_effective_billing_access

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"], dependencies=[Depends(get_verified_user)])


async def _enrich_subscription(sub: UserSubscription, db: AsyncSession) -> SubscriptionResponse:
    # After flush(), server defaults (created_at) may be expired; model_validate
    # would trigger a sync lazy load and raise MissingGreenlet in async SQLAlchemy.
    state = inspect(sub)
    if state.persistent and (state.expired or "created_at" in state.unloaded):
        await db.refresh(sub)

    ticker = (await db.execute(select(Ticker).where(Ticker.id == sub.ticker_id))).scalar_one()
    tf = (await db.execute(select(Timeframe).where(Timeframe.id == sub.timeframe_id))).scalar_one()
    ind = (await db.execute(select(IndicatorType).where(IndicatorType.id == sub.indicator_type_id))).scalar_one()
    resp = SubscriptionResponse.model_validate(sub)
    resp.ticker = ticker
    resp.timeframe = tf
    resp.indicator = ind
    return resp


async def _require_billing_access(user: User, db: AsyncSession):
    access = await get_effective_billing_access(db, user)
    if access.requires_upgrade:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=UPGRADE_REQUIRED_DETAIL)
    return access


@router.get("", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSubscription]:
    await _require_billing_access(user, db)
    result = await db.execute(
        select(UserSubscription)
        .where(UserSubscription.user_id == user.id)
        .options(
            selectinload(UserSubscription.user),
        )
    )
    subs = list(result.scalars().all())
    return [await _enrich_subscription(sub, db) for sub in subs]


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    access = await _require_billing_access(user, db)
    count_result = await db.execute(
        select(func.count()).select_from(UserSubscription).where(
            UserSubscription.user_id == user.id, UserSubscription.is_active.is_(True)
        )
    )
    if (count_result.scalar() or 0) >= access.max_subscriptions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription limit reached")

    for model, id_ in [(Ticker, body.ticker_id), (Timeframe, body.timeframe_id), (IndicatorType, body.indicator_type_id)]:
        row = (await db.execute(select(model).where(model.id == id_, model.is_active.is_(True)))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__tablename__} not found")

    existing = await db.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.ticker_id == body.ticker_id,
            UserSubscription.timeframe_id == body.timeframe_id,
            UserSubscription.indicator_type_id == body.indicator_type_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subscription already exists")

    bars = body.bars or min(get_settings().default_subscription_bars, access.max_bars)
    sub = UserSubscription(
        user_id=user.id,
        ticker_id=body.ticker_id,
        timeframe_id=body.timeframe_id,
        indicator_type_id=body.indicator_type_id,
        bars=bars,
    )
    db.add(sub)
    await db.flush()
    return await _enrich_subscription(sub, db)


@router.post("/bulk", response_model=SubscriptionBulkResponse, status_code=status.HTTP_201_CREATED)
async def create_subscriptions_bulk(
    body: SubscriptionBulkCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionBulkResponse:
    access = await _require_billing_access(user, db)
    unique_ticker_ids = list(dict.fromkeys(body.ticker_ids))

    tf = (
        await db.execute(
            select(Timeframe).where(Timeframe.id == body.timeframe_id, Timeframe.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if tf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="timeframes not found")

    indicator = (
        await db.execute(
            select(IndicatorType).where(
                IndicatorType.id == body.indicator_type_id, IndicatorType.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if indicator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="indicator_types not found")

    tickers_result = await db.execute(
        select(Ticker).where(Ticker.id.in_(unique_ticker_ids), Ticker.is_active.is_(True))
    )
    tickers_by_id = {t.id: t for t in tickers_result.scalars().all()}
    missing_ticker_ids = [tid for tid in unique_ticker_ids if tid not in tickers_by_id]
    if missing_ticker_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "tickers not found", "ticker_ids": [str(tid) for tid in missing_ticker_ids]},
        )

    existing_result = await db.execute(
        select(UserSubscription.ticker_id).where(
            UserSubscription.user_id == user.id,
            UserSubscription.timeframe_id == body.timeframe_id,
            UserSubscription.indicator_type_id == body.indicator_type_id,
            UserSubscription.ticker_id.in_(unique_ticker_ids),
        )
    )
    existing_ticker_ids = set(existing_result.scalars().all())

    count_result = await db.execute(
        select(func.count()).select_from(UserSubscription).where(
            UserSubscription.user_id == user.id, UserSubscription.is_active.is_(True)
        )
    )
    active_count = count_result.scalar() or 0
    to_create_ids = [tid for tid in unique_ticker_ids if tid not in existing_ticker_ids]
    if active_count + len(to_create_ids) > access.max_subscriptions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription limit reached")

    bars = body.bars or min(get_settings().default_subscription_bars, access.max_bars)
    created_subs: list[UserSubscription] = []
    for ticker_id in to_create_ids:
        sub = UserSubscription(
            user_id=user.id,
            ticker_id=ticker_id,
            timeframe_id=body.timeframe_id,
            indicator_type_id=body.indicator_type_id,
            bars=bars,
        )
        db.add(sub)
        created_subs.append(sub)

    await db.flush()
    created = [await _enrich_subscription(sub, db) for sub in created_subs]
    skipped = [tid for tid in unique_ticker_ids if tid in existing_ticker_ids]
    return SubscriptionBulkResponse(
        created=created,
        skipped_ticker_ids=skipped,
        created_count=len(created),
        skipped_count=len(skipped),
    )


@router.patch("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: UUID,
    body: SubscriptionUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    await _require_billing_access(user, db)
    result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.id == subscription_id, UserSubscription.user_id == user.id
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    if body.bars is not None:
        sub.bars = body.bars
    if body.is_active is not None:
        sub.is_active = body.is_active
    await db.flush()
    return await _enrich_subscription(sub, db)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.id == subscription_id, UserSubscription.user_id == user.id
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    await db.delete(sub)
