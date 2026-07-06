from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.db.models.billing import Plan, Subscription, UserPlanAddon
from backend.app.db.models.user import User
from backend.app.services.billing_access import get_effective_billing_access
from backend.app.services.billing_constants import (
    PLAN_KIND_ADDON,
    PLAN_KIND_INTERNAL,
    PLAN_KIND_SUBSCRIPTION,
)
from backend.app.services.billing_service import (
    apply_membership_activated,
    apply_membership_deactivated,
    list_public_plans,
)


@pytest.mark.asyncio
async def test_trial_user_gets_full_access(db_session, test_user):
    db_session.add(
        User(
            id=test_user.id,
            email=test_user.email,
            password_hash="hash",
            full_name=test_user.full_name,
            trading_style="day_trader",
            primary_market="forex",
            created_at=datetime.now(timezone.utc),
        )
    )
    free_plan = Plan(
        slug="free",
        name="Free",
        max_subscriptions=5,
        max_timeframes=2,
        price_cents=0,
        currency="USD",
        billing_interval="month",
        plan_kind=PLAN_KIND_INTERNAL,
    )
    db_session.add(free_plan)
    await db_session.flush()
    db_session.add(Subscription(user_id=test_user.id, plan_id=free_plan.id, status="active"))
    await db_session.flush()

    user = (await db_session.execute(select(User).where(User.id == test_user.id))).scalar_one()
    access = await get_effective_billing_access(db_session, user)
    assert access.trial_active is True
    assert access.requires_upgrade is False
    assert access.max_subscriptions == 100
    assert access.max_bars == 2500


@pytest.mark.asyncio
async def test_expired_trial_requires_upgrade(db_session, test_user):
    db_session.add(
        User(
            id=test_user.id,
            email=test_user.email,
            password_hash="hash",
            full_name=test_user.full_name,
            trading_style="day_trader",
            primary_market="forex",
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
    )
    free_plan = Plan(
        slug="free",
        name="Free",
        max_subscriptions=5,
        max_timeframes=2,
        price_cents=0,
        currency="USD",
        billing_interval="month",
        plan_kind=PLAN_KIND_INTERNAL,
    )
    db_session.add(free_plan)
    await db_session.flush()
    db_session.add(Subscription(user_id=test_user.id, plan_id=free_plan.id, status="active"))
    await db_session.flush()

    user = (await db_session.execute(select(User).where(User.id == test_user.id))).scalar_one()
    access = await get_effective_billing_access(db_session, user)
    assert access.trial_active is False
    assert access.requires_upgrade is True
    assert access.max_subscriptions == 0


@pytest.mark.asyncio
async def test_list_public_plans_hides_internal(db_session):
    db_session.add_all(
        [
            Plan(
                slug="free",
                name="Free",
                max_subscriptions=5,
                max_timeframes=2,
                price_cents=0,
                currency="USD",
                billing_interval="month",
                plan_kind=PLAN_KIND_INTERNAL,
            ),
            Plan(
                slug="pro",
                name="Pro",
                max_subscriptions=100,
                max_timeframes=8,
                price_cents=999,
                currency="USD",
                billing_interval="month",
                whop_plan_id="plan_pro",
                plan_kind=PLAN_KIND_SUBSCRIPTION,
            ),
            Plan(
                slug="addon-subs-50",
                name="+50 Subs",
                max_subscriptions=0,
                max_timeframes=0,
                price_cents=500,
                currency="USD",
                billing_interval="month",
                whop_plan_id="plan_addon",
                plan_kind=PLAN_KIND_ADDON,
                addon_bonus_subscriptions=50,
            ),
        ]
    )
    await db_session.flush()

    public = await list_public_plans(db_session, include_internal=False)
    slugs = {plan.slug for plan in public}
    assert slugs == {"pro", "addon-subs-50"}

    all_plans = await list_public_plans(db_session, include_internal=True)
    assert len(all_plans) == 3


@pytest.mark.asyncio
async def test_addon_membership_increases_bonus(db_session, test_user):
    db_session.add(
        User(
            id=test_user.id,
            email=test_user.email,
            password_hash="hash",
            full_name=test_user.full_name,
            trading_style="day_trader",
            primary_market="forex",
        )
    )
    free_plan = Plan(
        slug="free",
        name="Free",
        max_subscriptions=5,
        max_timeframes=2,
        price_cents=0,
        currency="USD",
        billing_interval="month",
        plan_kind=PLAN_KIND_INTERNAL,
    )
    pro_plan = Plan(
        slug="pro",
        name="Pro",
        max_subscriptions=100,
        max_timeframes=8,
        price_cents=999,
        currency="USD",
        billing_interval="month",
        whop_plan_id="plan_pro_addon",
        plan_kind=PLAN_KIND_SUBSCRIPTION,
    )
    addon_plan = Plan(
        slug="addon-subs-50",
        name="+50",
        max_subscriptions=0,
        max_timeframes=0,
        price_cents=500,
        currency="USD",
        billing_interval="month",
        whop_plan_id="plan_addon_test",
        plan_kind=PLAN_KIND_ADDON,
        addon_bonus_subscriptions=50,
    )
    db_session.add_all([free_plan, pro_plan, addon_plan])
    await db_session.flush()
    billing_sub = Subscription(user_id=test_user.id, plan_id=pro_plan.id, status="active", provider="whop")
    db_session.add(billing_sub)
    await db_session.flush()

    membership = SimpleNamespace(
        id="mem_addon_1",
        status="active",
        metadata={"tradeeye_user_id": str(test_user.id)},
        plan=SimpleNamespace(id="plan_addon_test", metadata=None),
        user=SimpleNamespace(id="whop_u", email=test_user.email),
        renewal_period_start=datetime.now(timezone.utc),
        renewal_period_end=datetime.now(timezone.utc),
        canceled_at=None,
    )
    await apply_membership_activated(db_session, membership)
    await db_session.refresh(billing_sub)
    assert billing_sub.bonus_subscriptions == 50
    assert billing_sub.plan_id == pro_plan.id

    await apply_membership_deactivated(db_session, membership)
    await db_session.refresh(billing_sub)
    assert billing_sub.bonus_subscriptions == 0
