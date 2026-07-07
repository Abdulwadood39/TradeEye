from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.db.models.billing import Plan, Subscription, UserPlanAddon
from backend.app.db.models.user import EmailVerificationToken, User, UserSubscription
from backend.app.services.billing_constants import PLAN_KIND_INTERNAL, PLAN_KIND_SUBSCRIPTION
from backend.app.services.user_service import UserDeletionError, delete_user_account, get_admin_user_stats


@pytest.mark.asyncio
async def test_delete_user_account_removes_related_rows(db_session):
    user_id = uuid4()
    user = User(
        id=user_id,
        email="delete-me@example.com",
        password_hash="hash",
        full_name="Delete Me",
        trading_style="day_trader",
        primary_market="forex",
        email_verified_at=datetime.now(timezone.utc),
    )
    free_plan = Plan(
        slug="free-del",
        name="Free",
        max_subscriptions=5,
        max_timeframes=2,
        price_cents=0,
        currency="USD",
        billing_interval="month",
        plan_kind=PLAN_KIND_INTERNAL,
    )
    db_session.add_all([user, free_plan])
    await db_session.flush()

    billing_sub = Subscription(user_id=user_id, plan_id=free_plan.id, status="active")
    db_session.add(billing_sub)
    db_session.add(
        EmailVerificationToken(
            user_id=user_id,
            token_hash="abc",
            expires_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()

    await delete_user_account(db_session, user_id)
    await db_session.commit()

    assert (await db_session.execute(select(User).where(User.id == user_id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Subscription).where(Subscription.user_id == user_id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_admin_user_stats_counts_paid_and_addons(db_session):
    user_free = User(
        email="free@example.com",
        password_hash="hash",
        full_name="Free",
        trading_style="day_trader",
        primary_market="forex",
    )
    user_paid = User(
        email="paid@example.com",
        password_hash="hash",
        full_name="Paid",
        trading_style="day_trader",
        primary_market="forex",
    )
    free_plan = Plan(
        slug="free-stats",
        name="Free",
        max_subscriptions=5,
        max_timeframes=2,
        price_cents=0,
        currency="USD",
        billing_interval="month",
        plan_kind=PLAN_KIND_INTERNAL,
    )
    pro_plan = Plan(
        slug="pro-stats",
        name="Pro",
        max_subscriptions=100,
        max_timeframes=8,
        price_cents=999,
        currency="USD",
        billing_interval="month",
        whop_plan_id="plan_stats",
        plan_kind=PLAN_KIND_SUBSCRIPTION,
    )
    db_session.add_all([user_free, user_paid, free_plan, pro_plan])
    await db_session.flush()

    db_session.add(Subscription(user_id=user_free.id, plan_id=free_plan.id, status="active"))
    billing_paid = Subscription(
        user_id=user_paid.id,
        plan_id=pro_plan.id,
        status="active",
        provider="whop",
        provider_subscription_id="mem_stats",
    )
    db_session.add(billing_paid)
    await db_session.flush()
    db_session.add(
        UserPlanAddon(
            subscription_id=billing_paid.id,
            plan_id=pro_plan.id,
            provider_membership_id="addon_mem_1",
            bonus_subscriptions=50,
            status="active",
        )
    )
    await db_session.flush()

    stats = await get_admin_user_stats(db_session)
    assert stats.registered_users == 2
    assert stats.paid_users == 1
    assert stats.addons_sold == 1


@pytest.mark.asyncio
async def test_cannot_delete_admin_test_user(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_TEST_USER_EMAIL", "protected@example.com")
    from backend.app.core.config import get_settings

    get_settings.cache_clear()

    user = User(
        email="protected@example.com",
        password_hash="hash",
        full_name="Admin",
        trading_style="day_trader",
        primary_market="forex",
    )
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(UserDeletionError, match="cannot be deleted"):
        await delete_user_account(db_session, user.id)

    get_settings.cache_clear()
