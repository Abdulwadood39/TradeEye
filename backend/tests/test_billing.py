from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.db.models.billing import Plan, Subscription
from backend.app.db.models.user import User
from backend.app.db.models.user import User
from backend.app.services.billing_service import (
    apply_membership_activated,
    apply_membership_deactivated,
    create_checkout_url,
    record_billing_event,
)


@pytest.mark.asyncio
async def test_apply_membership_activated_by_metadata(db_session, test_user):
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
    await db_session.flush()

    pro_plan = Plan(
        slug="pro-test",
        name="Pro Test",
        max_subscriptions=50,
        max_timeframes=8,
        price_cents=999,
        currency="USD",
        billing_interval="month",
        whop_plan_id="plan_test_pro",
    )
    free_plan = Plan(
        slug="free-test",
        name="Free Test",
        max_subscriptions=5,
        max_timeframes=2,
        price_cents=0,
        currency="USD",
        billing_interval="month",
    )
    db_session.add_all([pro_plan, free_plan])
    await db_session.flush()

    db_session.add(Subscription(user_id=test_user.id, plan_id=free_plan.id, status="active"))
    await db_session.flush()

    membership = SimpleNamespace(
        id="mem_test_123",
        status="active",
        metadata={"tradeeye_user_id": str(test_user.id)},
        plan=SimpleNamespace(id="plan_test_pro", metadata=None),
        user=SimpleNamespace(id="user_whop_1", email=test_user.email),
        renewal_period_start=datetime.now(timezone.utc),
        renewal_period_end=datetime.now(timezone.utc),
        canceled_at=None,
    )

    updated = await apply_membership_activated(db_session, membership)
    assert updated is not None
    assert updated.plan_id == pro_plan.id
    assert updated.provider == "whop"
    assert updated.provider_subscription_id == "mem_test_123"


@pytest.mark.asyncio
async def test_apply_membership_deactivated_downgrades_to_free(db_session, test_user):
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
    await db_session.flush()

    free_plan = Plan(
        slug="free",
        name="Free",
        max_subscriptions=5,
        max_timeframes=2,
        price_cents=0,
        currency="USD",
        billing_interval="month",
    )
    pro_plan = Plan(
        slug="pro-downgrade",
        name="Pro",
        max_subscriptions=50,
        max_timeframes=8,
        price_cents=999,
        currency="USD",
        billing_interval="month",
        whop_plan_id="plan_downgrade",
    )
    db_session.add_all([free_plan, pro_plan])
    await db_session.flush()

    billing_sub = Subscription(
        user_id=test_user.id,
        plan_id=pro_plan.id,
        status="active",
        provider="whop",
        provider_subscription_id="mem_downgrade",
    )
    db_session.add(billing_sub)
    await db_session.flush()

    membership = SimpleNamespace(
        id="mem_downgrade",
        status="canceled",
        metadata=None,
        plan=SimpleNamespace(id="plan_downgrade", metadata=None),
        user=SimpleNamespace(id="user_whop_2", email=test_user.email),
        renewal_period_end=datetime.now(timezone.utc),
        canceled_at=datetime.now(timezone.utc),
    )

    updated = await apply_membership_deactivated(db_session, membership)
    assert updated is not None
    assert updated.plan_id == free_plan.id
    assert updated.status == "canceled"


@pytest.mark.asyncio
async def test_record_billing_event_is_idempotent(db_session):
    event = await record_billing_event(
        db_session,
        event_id="evt_123",
        event_type="membership.activated",
        payload={"id": "evt_123"},
    )
    assert event is not None

    duplicate = await record_billing_event(
        db_session,
        event_id="evt_123",
        event_type="membership.activated",
        payload={"id": "evt_123"},
    )
    assert duplicate is None


@pytest.mark.asyncio
async def test_create_checkout_url_uses_plan_purchase_url(monkeypatch, test_user):
    plan = Plan(
        slug="pro",
        name="Pro",
        max_subscriptions=100,
        max_timeframes=8,
        price_cents=999,
        currency="USD",
        billing_interval="month",
        whop_plan_id="plan_ZUwmW7PbwcLEF",
    )

    monkeypatch.setattr("backend.app.services.billing_service.get_whop_client", lambda: None)

    url = await create_checkout_url(plan=plan, user=test_user)
    assert "plan_ZUwmW7PbwcLEF" in url
    assert "billing-test%40example.com" in url
    assert str(test_user.id) in url
