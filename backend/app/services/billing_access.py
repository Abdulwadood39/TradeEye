from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import is_admin_test_user
from backend.app.core.config import Settings, get_settings
from backend.app.db.models.billing import Plan, Subscription, UserPlanAddon
from backend.app.db.models.catalog import Timeframe
from backend.app.db.models.user import User
from backend.app.services.billing_constants import (
    ACTIVE_BILLING_STATUSES,
    ADMIN_PLAN_SLUG,
    FREE_PLAN_SLUG,
    PLAN_KIND_ADDON,
    PLAN_KIND_INTERNAL,
    PLAN_KIND_SUBSCRIPTION,
)
from backend.app.services.billing_service import get_user_billing_subscription

UPGRADE_REQUIRED_DETAIL = {
    "code": "UPGRADE_REQUIRED",
    "message": "Your free trial has ended. Upgrade to Pro to continue.",
}


@dataclass(frozen=True)
class EffectiveBillingAccess:
    plan: Plan
    billing_sub: Subscription | None
    max_subscriptions: int
    max_timeframes: int
    max_bars: int
    trial_active: bool
    trial_ends_at: datetime | None
    requires_upgrade: bool
    is_paid: bool
    bonus_subscriptions: int


def _trial_ends_at(user: User, settings: Settings) -> datetime:
    created = user.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created + timedelta(days=settings.trial_days)


def _is_paid_subscription(billing_sub: Subscription | None, plan: Plan) -> bool:
    if billing_sub is None:
        return False
    if plan.plan_kind == PLAN_KIND_INTERNAL:
        return False
    if plan.plan_kind == PLAN_KIND_ADDON:
        return False
    if not plan.whop_plan_id or plan.price_cents <= 0:
        return False
    return billing_sub.status in ACTIVE_BILLING_STATUSES and billing_sub.provider == "whop"


async def _count_active_timeframes(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(Timeframe).where(Timeframe.is_active.is_(True)))
    return int(result.scalar() or 0)


async def get_effective_billing_access(
    db: AsyncSession,
    user: User,
    *,
    settings: Settings | None = None,
) -> EffectiveBillingAccess:
    settings = settings or get_settings()
    billing_sub = await get_user_billing_subscription(db, user.id)

    if billing_sub is None:
        raise ValueError("No billing plan assigned")

    plan_result = await db.execute(select(Plan).where(Plan.id == billing_sub.plan_id))
    plan = plan_result.scalar_one()

    bonus = billing_sub.bonus_subscriptions or 0
    max_bars = settings.default_subscription_bars
    trial_ends = _trial_ends_at(user, settings)
    now = datetime.now(timezone.utc)
    trial_active = now < trial_ends
    paid = _is_paid_subscription(billing_sub, plan)

    if is_admin_test_user(user) or plan.slug == ADMIN_PLAN_SLUG:
        return EffectiveBillingAccess(
            plan=plan,
            billing_sub=billing_sub,
            max_subscriptions=plan.max_subscriptions + bonus,
            max_timeframes=plan.max_timeframes,
            max_bars=max_bars,
            trial_active=False,
            trial_ends_at=None,
            requires_upgrade=False,
            is_paid=True,
            bonus_subscriptions=bonus,
        )

    if paid:
        return EffectiveBillingAccess(
            plan=plan,
            billing_sub=billing_sub,
            max_subscriptions=plan.max_subscriptions + bonus,
            max_timeframes=plan.max_timeframes,
            max_bars=max_bars,
            trial_active=False,
            trial_ends_at=trial_ends if trial_active else None,
            requires_upgrade=False,
            is_paid=True,
            bonus_subscriptions=bonus,
        )

    if trial_active:
        timeframe_count = await _count_active_timeframes(db)
        return EffectiveBillingAccess(
            plan=plan,
            billing_sub=billing_sub,
            max_subscriptions=settings.trial_max_subscriptions,
            max_timeframes=min(settings.trial_max_timeframes, timeframe_count),
            max_bars=max_bars,
            trial_active=True,
            trial_ends_at=trial_ends,
            requires_upgrade=False,
            is_paid=False,
            bonus_subscriptions=0,
        )

    return EffectiveBillingAccess(
        plan=plan,
        billing_sub=billing_sub,
        max_subscriptions=0,
        max_timeframes=0,
        max_bars=0,
        trial_active=False,
        trial_ends_at=trial_ends,
        requires_upgrade=True,
        is_paid=False,
        bonus_subscriptions=bonus,
    )

