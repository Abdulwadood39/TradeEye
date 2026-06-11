from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, uuid_pk


class ScanRun(TimestampMixin, Base):
    __tablename__ = "scan_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    timeframe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("timeframes.id"), nullable=False)
    indicator_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("indicator_types.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    tickers_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trends_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class TrendEvent(TimestampMixin, Base):
    __tablename__ = "trend_events"
    __table_args__ = (
        UniqueConstraint(
            "scan_run_id", "ticker_id", "timeframe_id", "indicator_type_id", "bars_scanned",
            name="uq_trend_event_per_scan",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    scan_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scan_runs.id"), nullable=False)
    ticker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tickers.id"), nullable=False)
    timeframe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("timeframes.id"), nullable=False)
    indicator_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("indicator_types.id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    bars_scanned: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationMessage(TimestampMixin, Base):
    __tablename__ = "notification_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tickers.id"), nullable=False)
    timeframe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("timeframes.id"), nullable=False)
    bars_scanned: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trend_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trend_events.id"), nullable=True
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
