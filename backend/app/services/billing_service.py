from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from whop_sdk import BadRequestError, PermissionDeniedError, Whop

from backend.app.core.config import Settings, get_settings
from backend.app.db.models.billing import BillingEvent, Plan, Subscription, UserPlanAddon
from backend.app.db.models.user import User
from backend.app.services.billing_constants import (
    ACTIVE_BILLING_STATUSES,
    ADMIN_PLAN_SLUG,
    BILLING_PROVIDER,
    FREE_PLAN_SLUG,
    PLAN_KIND_ADDON,
    PLAN_KIND_INTERNAL,
    PLAN_KIND_SUBSCRIPTION,
)
from backend.app.services.whop_client import get_whop_client

logger = logging.getLogger(__name__)


async def recalculate_bonus_subscriptions(db: AsyncSession, billing_sub: Subscription) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(UserPlanAddon.bonus_subscriptions), 0)).where(
            UserPlanAddon.subscription_id == billing_sub.id,
            UserPlanAddon.status == "active",
        )
    )
    total = int(result.scalar() or 0)
    billing_sub.bonus_subscriptions = total
    await db.flush()
    return total

from backend.app.services.billing_constants import (
    ACTIVE_BILLING_STATUSES,
    ADMIN_PLAN_SLUG,
    BILLING_PROVIDER,
    FREE_PLAN_SLUG,
    PLAN_KIND_ADDON,
    PLAN_KIND_INTERNAL,
    PLAN_KIND_SUBSCRIPTION,
)


def plan_to_response(plan: Plan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "slug": plan.slug,
        "name": plan.name,
        "max_subscriptions": plan.max_subscriptions,
        "max_timeframes": plan.max_timeframes,
        "price_cents": plan.price_cents,
        "currency": plan.currency,
        "billing_interval": plan.billing_interval,
        "is_active": plan.is_active,
        "whop_plan_id": plan.whop_plan_id,
        "plan_kind": plan.plan_kind,
        "addon_bonus_subscriptions": plan.addon_bonus_subscriptions,
        "is_paid": bool(plan.whop_plan_id and plan.price_cents > 0),
        "is_addon": plan.plan_kind == PLAN_KIND_ADDON,
    }


def _append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({k: v for k, v in params.items() if v})
    return urlunparse(parsed._replace(query=urlencode(query)))


def _metadata_user_id(metadata: dict[str, Any] | None) -> UUID | None:
    if not metadata:
        return None
    raw = metadata.get("tradeeye_user_id") or metadata.get("user_id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


async def get_user_billing_subscription(db: AsyncSession, user_id: UUID) -> Subscription | None:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    return result.scalar_one_or_none()


async def get_free_plan(db: AsyncSession) -> Plan | None:
    result = await db.execute(select(Plan).where(Plan.slug == FREE_PLAN_SLUG))
    return result.scalar_one_or_none()


async def resolve_plan_for_whop_id(db: AsyncSession, whop_plan_id: str) -> Plan | None:
    result = await db.execute(select(Plan).where(Plan.whop_plan_id == whop_plan_id, Plan.is_active.is_(True)))
    return result.scalar_one_or_none()


async def list_public_plans(db: AsyncSession, *, include_internal: bool = False) -> list[Plan]:
    query = select(Plan).where(Plan.is_active.is_(True))
    if not include_internal:
        query = query.where(
            Plan.whop_plan_id.isnot(None),
            Plan.plan_kind.in_((PLAN_KIND_SUBSCRIPTION, PLAN_KIND_ADDON)),
        )
    result = await db.execute(query.order_by(Plan.price_cents, Plan.name))
    return list(result.scalars().all())


def _create_checkout_configuration_sync(
    client: Whop,
    *,
    whop_plan_id: str,
    user_id: UUID,
    user_email: str,
    redirect_url: str,
) -> str | None:
    try:
        checkout = client.checkout_configurations.create(
            plan_id=whop_plan_id,
            metadata={
                "tradeeye_user_id": str(user_id),
                "tradeeye_email": user_email,
            },
            redirect_url=redirect_url,
        )
        if checkout.purchase_url:
            return checkout.purchase_url
    except (BadRequestError, PermissionDeniedError) as exc:
        logger.info("Whop checkout configuration unavailable, using plan purchase URL: %s", exc)
    except Exception:
        logger.exception("Unexpected Whop checkout configuration error")
    return None


async def create_checkout_url(
    *,
    plan: Plan,
    user: User,
    settings: Settings | None = None,
) -> str:
    if not plan.whop_plan_id:
        raise ValueError("Plan is not linked to Whop")

    settings = settings or get_settings()
    client = get_whop_client()
    purchase_url = f"https://whop.com/checkout/{plan.whop_plan_id}"

    if client is not None:
        configured_url = await asyncio.to_thread(
            _create_checkout_configuration_sync,
            client,
            whop_plan_id=plan.whop_plan_id,
            user_id=user.id,
            user_email=user.email,
            redirect_url=settings.whop_billing_success_url,
        )
        if configured_url:
            purchase_url = configured_url

    return _append_query_params(
        purchase_url,
        {
            "email": user.email,
            "metadata[tradeeye_user_id]": str(user.id),
        },
    )


async def _resolve_user_for_membership(db: AsyncSession, membership: Any) -> User | None:
    metadata = getattr(membership, "metadata", None) or {}
    user_id = _metadata_user_id(metadata)
    if user_id is not None:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is not None:
            return user

    plan_meta = getattr(getattr(membership, "plan", None), "metadata", None) or {}
    user_id = _metadata_user_id(plan_meta)
    if user_id is not None:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is not None:
            return user

    whop_user = getattr(membership, "user", None)
    email = getattr(whop_user, "email", None) if whop_user is not None else None
    if email:
        result = await db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    membership_id = getattr(membership, "id", None)
    if membership_id:
        result = await db.execute(
            select(Subscription).where(
                Subscription.provider == BILLING_PROVIDER,
                Subscription.provider_subscription_id == membership_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            user_result = await db.execute(select(User).where(User.id == existing.user_id))
            return user_result.scalar_one_or_none()

    return None


async def _ensure_billing_subscription(db: AsyncSession, user: User) -> Subscription:
    existing = await get_user_billing_subscription(db, user.id)
    if existing is not None:
        return existing

    free_plan = await get_free_plan(db)
    if free_plan is None:
        raise RuntimeError("Free plan is not configured")

    sub = Subscription(user_id=user.id, plan_id=free_plan.id, status="active")
    db.add(sub)
    await db.flush()
    return sub


async def apply_membership_activated(db: AsyncSession, membership: Any) -> Subscription | None:
    user = await _resolve_user_for_membership(db, membership)
    if user is None:
        logger.warning("Could not resolve TradeEye user for Whop membership %s", getattr(membership, "id", None))
        return None

    whop_plan_id = getattr(getattr(membership, "plan", None), "id", None)
    if not whop_plan_id:
        logger.warning("Whop membership %s missing plan id", getattr(membership, "id", None))
        return None

    plan = await resolve_plan_for_whop_id(db, whop_plan_id)
    if plan is None:
        logger.warning("No TradeEye plan mapped for Whop plan %s", whop_plan_id)
        return None

    billing_sub = await _ensure_billing_subscription(db, user)
    membership_id = getattr(membership, "id", None)
    status = _normalize_membership_status(getattr(membership, "status", None))

    if plan.plan_kind == PLAN_KIND_ADDON:
        if not membership_id:
            return billing_sub
        existing = await db.execute(
            select(UserPlanAddon).where(UserPlanAddon.provider_membership_id == membership_id)
        )
        addon = existing.scalar_one_or_none()
        if addon is None:
            addon = UserPlanAddon(
                subscription_id=billing_sub.id,
                plan_id=plan.id,
                provider_membership_id=membership_id,
                bonus_subscriptions=plan.addon_bonus_subscriptions,
                status=status,
            )
            db.add(addon)
        else:
            addon.status = status
            addon.bonus_subscriptions = plan.addon_bonus_subscriptions
        await recalculate_bonus_subscriptions(db, billing_sub)
        await db.flush()
        return billing_sub

    billing_sub.plan_id = plan.id
    billing_sub.status = status
    billing_sub.provider = BILLING_PROVIDER
    billing_sub.provider_subscription_id = membership_id
    whop_user = getattr(membership, "user", None)
    billing_sub.provider_customer_id = getattr(whop_user, "id", None) if whop_user is not None else None
    billing_sub.current_period_start = getattr(membership, "renewal_period_start", None)
    billing_sub.current_period_end = getattr(membership, "renewal_period_end", None)
    billing_sub.canceled_at = getattr(membership, "canceled_at", None)
    await db.flush()
    return billing_sub


async def apply_membership_deactivated(db: AsyncSession, membership: Any) -> Subscription | None:
    user = await _resolve_user_for_membership(db, membership)
    if user is None:
        return None

    billing_sub = await get_user_billing_subscription(db, user.id)
    if billing_sub is None:
        return None

    membership_id = getattr(membership, "id", None)
    whop_plan_id = getattr(getattr(membership, "plan", None), "id", None)
    plan = await resolve_plan_for_whop_id(db, whop_plan_id) if whop_plan_id else None

    if plan is not None and plan.plan_kind == PLAN_KIND_ADDON and membership_id:
        addon_result = await db.execute(
            select(UserPlanAddon).where(UserPlanAddon.provider_membership_id == membership_id)
        )
        addon = addon_result.scalar_one_or_none()
        if addon is not None:
            addon.status = "canceled"
        await recalculate_bonus_subscriptions(db, billing_sub)
        await db.flush()
        return billing_sub

    free_plan = await get_free_plan(db)
    if free_plan is None:
        billing_sub.status = "canceled"
    else:
        billing_sub.plan_id = free_plan.id
        billing_sub.status = "canceled"
    billing_sub.canceled_at = getattr(membership, "canceled_at", None) or datetime.now(timezone.utc)
    billing_sub.current_period_end = getattr(membership, "renewal_period_end", None)
    await db.flush()
    return billing_sub


def _normalize_membership_status(status: str | None) -> str:
    if status in ACTIVE_BILLING_STATUSES:
        return "active"
    if status in {"canceled", "expired", "completed"}:
        return "canceled"
    return status or "active"


async def record_billing_event(
    db: AsyncSession,
    *,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> BillingEvent | None:
    existing = await db.execute(
        select(BillingEvent).where(BillingEvent.external_event_id == event_id)
    )
    if existing.scalar_one_or_none() is not None:
        return None

    event = BillingEvent(
        provider=BILLING_PROVIDER,
        external_event_id=event_id,
        event_type=event_type,
        payload_json=payload,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.flush()
    return event


async def process_whop_webhook_event(db: AsyncSession, event: Any) -> None:
    event_id = getattr(event, "id", None)
    event_type = getattr(event, "type", None)
    if not event_id or not event_type:
        return

    payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
    if await record_billing_event(db, event_id=event_id, event_type=event_type, payload=payload) is None:
        logger.info("Skipping duplicate Whop webhook %s", event_id)
        return

    data = getattr(event, "data", None)
    if event_type == "membership.activated":
        await apply_membership_activated(db, data)
    elif event_type == "membership.deactivated":
        await apply_membership_deactivated(db, data)
    elif event_type == "membership.cancel_at_period_end_changed" and data is not None:
        user = await _resolve_user_for_membership(db, data)
        if user is None:
            return
        billing_sub = await get_user_billing_subscription(db, user.id)
        if billing_sub is None:
            return
        billing_sub.status = _normalize_membership_status(getattr(data, "status", None))
        billing_sub.canceled_at = getattr(data, "canceled_at", None)
        billing_sub.current_period_end = getattr(data, "renewal_period_end", None)
        await db.flush()

    await db.commit()
