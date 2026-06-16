from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, uuid_fk, uuid_pk
from backend.app.db.types import UTCDateTime


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    max_subscriptions: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_timeframes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(16), default="month", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", unique=True, nullable=False)
    plan_id: Mapped[uuid.UUID] = uuid_fk("plans.id", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    provider_customer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_subscription_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)


class BillingEvent(TimestampMixin, Base):
    __tablename__ = "billing_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    processed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
