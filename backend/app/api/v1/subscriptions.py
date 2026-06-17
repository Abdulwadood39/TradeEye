from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_verified_user
from backend.app.core.config import get_settings
from backend.app.db.models.billing import Plan, Subscription
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe
from backend.app.db.models.user import User, UserSubscription
from backend.app.db.session import get_db
from backend.app.schemas.catalog import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"], dependencies=[Depends(get_verified_user)])


async def _check_plan_limits(user: User, db: AsyncSession) -> Plan:
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id).options()
    )
    billing_sub = sub_result.scalar_one_or_none()
    if billing_sub is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No billing plan assigned")
    plan_result = await db.execute(select(Plan).where(Plan.id == billing_sub.plan_id))
    return plan_result.scalar_one()


@router.get("", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSubscription]:
    result = await db.execute(
        select(UserSubscription)
        .where(UserSubscription.user_id == user.id)
        .options(
            selectinload(UserSubscription.user),
        )
    )
    subs = list(result.scalars().all())
    enriched = []
    for sub in subs:
        ticker = (await db.execute(select(Ticker).where(Ticker.id == sub.ticker_id))).scalar_one()
        tf = (await db.execute(select(Timeframe).where(Timeframe.id == sub.timeframe_id))).scalar_one()
        ind = (await db.execute(select(IndicatorType).where(IndicatorType.id == sub.indicator_type_id))).scalar_one()
        resp = SubscriptionResponse.model_validate(sub)
        resp.ticker = ticker
        resp.timeframe = tf
        resp.indicator = ind
        enriched.append(resp)
    return enriched


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    plan = await _check_plan_limits(user, db)
    count_result = await db.execute(
        select(func.count()).select_from(UserSubscription).where(
            UserSubscription.user_id == user.id, UserSubscription.is_active.is_(True)
        )
    )
    if (count_result.scalar() or 0) >= plan.max_subscriptions:
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

    bars = body.bars or get_settings().default_subscription_bars
    sub = UserSubscription(
        user_id=user.id,
        ticker_id=body.ticker_id,
        timeframe_id=body.timeframe_id,
        indicator_type_id=body.indicator_type_id,
        bars=bars,
    )
    db.add(sub)
    await db.flush()

    ticker = (await db.execute(select(Ticker).where(Ticker.id == sub.ticker_id))).scalar_one()
    tf = (await db.execute(select(Timeframe).where(Timeframe.id == sub.timeframe_id))).scalar_one()
    ind = (await db.execute(select(IndicatorType).where(IndicatorType.id == sub.indicator_type_id))).scalar_one()
    resp = SubscriptionResponse.model_validate(sub)
    resp.ticker = ticker
    resp.timeframe = tf
    resp.indicator = ind
    return resp


@router.patch("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: UUID,
    body: SubscriptionUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
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
    ticker = (await db.execute(select(Ticker).where(Ticker.id == sub.ticker_id))).scalar_one()
    tf = (await db.execute(select(Timeframe).where(Timeframe.id == sub.timeframe_id))).scalar_one()
    ind = (await db.execute(select(IndicatorType).where(IndicatorType.id == sub.indicator_type_id))).scalar_one()
    resp = SubscriptionResponse.model_validate(sub)
    resp.ticker = ticker
    resp.timeframe = tf
    resp.indicator = ind
    return resp


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
