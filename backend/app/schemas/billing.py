from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PlanResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    max_subscriptions: int
    max_timeframes: int
    price_cents: int
    currency: str
    billing_interval: str
    is_active: bool
    whop_plan_id: Optional[str] = None
    plan_kind: str = "subscription"
    addon_bonus_subscriptions: int = 0
    is_paid: bool = False
    is_addon: bool = False

    model_config = {"from_attributes": True}


class BillingAccessResponse(BaseModel):
    max_subscriptions: int
    max_timeframes: int
    max_bars: int
    trial_active: bool
    trial_ends_at: Optional[datetime] = None
    requires_upgrade: bool
    is_paid: bool
    bonus_subscriptions: int = 0


class BillingSubscriptionResponse(BaseModel):
    status: str
    provider: Optional[str] = None
    provider_membership_id: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    manage_url: Optional[str] = None


class BillingStatusResponse(BaseModel):
    plan: PlanResponse
    subscription: BillingSubscriptionResponse
    access: BillingAccessResponse


class CheckoutRequest(BaseModel):
    plan_slug: str = Field(min_length=1, max_length=64)


class CheckoutResponse(BaseModel):
    checkout_url: str
    plan_slug: str
    whop_plan_id: str
