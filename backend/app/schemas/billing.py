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
    is_paid: bool = False

    model_config = {"from_attributes": True}


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


class CheckoutRequest(BaseModel):
    plan_slug: str = Field(min_length=1, max_length=64)


class CheckoutResponse(BaseModel):
    checkout_url: str
    plan_slug: str
    whop_plan_id: str
