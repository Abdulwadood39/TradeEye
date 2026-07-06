from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_verified_user, is_admin_test_user
from backend.app.core.config import get_settings
from backend.app.db.models.billing import Plan, Subscription
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.schemas.billing import (
    BillingAccessResponse,
    BillingStatusResponse,
    BillingSubscriptionResponse,
    CheckoutRequest,
    CheckoutResponse,
    PlanResponse,
)
from backend.app.services.billing_access import get_effective_billing_access
from backend.app.services.billing_constants import PLAN_KIND_ADDON, PLAN_KIND_INTERNAL
from backend.app.services.billing_service import create_checkout_url, list_public_plans, plan_to_response

router = APIRouter(prefix="/billing", tags=["billing"], dependencies=[Depends(get_verified_user)])


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[PlanResponse]:
    plans = await list_public_plans(db, include_internal=is_admin_test_user(user))
    return [PlanResponse(**plan_to_response(plan)) for plan in plans]


@router.get("/status", response_model=BillingStatusResponse)
async def billing_status(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> BillingStatusResponse:
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    billing_sub = sub_result.scalar_one_or_none()
    if billing_sub is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No billing plan assigned")

    access = await get_effective_billing_access(db, user)

    return BillingStatusResponse(
        plan=PlanResponse(**plan_to_response(access.plan)),
        subscription=BillingSubscriptionResponse(
            status=billing_sub.status,
            provider=billing_sub.provider,
            provider_membership_id=billing_sub.provider_subscription_id,
            current_period_start=billing_sub.current_period_start,
            current_period_end=billing_sub.current_period_end,
            canceled_at=billing_sub.canceled_at,
        ),
        access=BillingAccessResponse(
            max_subscriptions=access.max_subscriptions,
            max_timeframes=access.max_timeframes,
            max_bars=access.max_bars,
            trial_active=access.trial_active,
            trial_ends_at=access.trial_ends_at,
            requires_upgrade=access.requires_upgrade,
            is_paid=access.is_paid,
            bonus_subscriptions=access.bonus_subscriptions,
        ),
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(
    body: CheckoutRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    settings = get_settings()
    if not settings.whop_configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured")

    plan_result = await db.execute(
        select(Plan).where(Plan.slug == body.plan_slug, Plan.is_active.is_(True))
    )
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    if plan.plan_kind == PLAN_KIND_INTERNAL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan is not available for purchase")
    if not plan.whop_plan_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan is not available for purchase")

    if plan.plan_kind == PLAN_KIND_ADDON:
        access = await get_effective_billing_access(db, user)
        if not access.is_paid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Add-ons require an active Pro subscription",
            )

    try:
        checkout_url = await create_checkout_url(plan=plan, user=user, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return CheckoutResponse(
        checkout_url=checkout_url,
        plan_slug=plan.slug,
        whop_plan_id=plan.whop_plan_id,
    )
