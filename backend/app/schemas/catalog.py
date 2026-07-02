from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TickerResponse(BaseModel):
    id: UUID
    yfinance_symbol: str
    display_name: str
    category: str
    is_active: bool

    model_config = {"from_attributes": True}


class TimeframeResponse(BaseModel):
    id: UUID
    code: str
    label: str
    is_active: bool

    model_config = {"from_attributes": True}


class IndicatorResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    ticker_id: UUID
    timeframe_id: UUID
    indicator_type_id: UUID
    bars: int = Field(ge=50, le=10000)


class SubscriptionBulkCreate(BaseModel):
    ticker_ids: list[UUID] = Field(min_length=1)
    timeframe_id: UUID
    indicator_type_id: UUID
    bars: int | None = Field(default=None, ge=50, le=10000)


class SubscriptionBulkResponse(BaseModel):
    created: list[SubscriptionResponse]
    skipped_ticker_ids: list[UUID]
    created_count: int
    skipped_count: int


class SubscriptionUpdate(BaseModel):
    bars: Optional[int] = Field(default=None, ge=50, le=10000)
    is_active: Optional[bool] = None


class SubscriptionResponse(BaseModel):
    id: UUID
    ticker_id: UUID
    timeframe_id: UUID
    indicator_type_id: UUID
    bars: int
    is_active: bool
    created_at: datetime
    ticker: Optional[TickerResponse] = None
    timeframe: Optional[TimeframeResponse] = None
    indicator: Optional[IndicatorResponse] = None

    model_config = {"from_attributes": True}


class NotificationSettingsUpdate(BaseModel):
    discord_webhook_url: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    preferred_channel: Optional[str] = Field(default=None, pattern="^(discord|telegram|both)$")
    delete_previous_messages: Optional[bool] = None


class NotificationSettingsResponse(BaseModel):
    preferred_channel: str
    delete_previous_messages: bool
    notify_on: str
    has_discord: bool
    has_telegram: bool

    model_config = {"from_attributes": True}


class TrendItemResponse(BaseModel):
    id: UUID
    display_name: str
    yfinance_symbol: str
    timeframe: str
    direction: str
    bars_scanned: int
    score: int
    confidence: float
    scanned_at: datetime


class TrendListResponse(BaseModel):
    items: list[TrendItemResponse]
    total: int
    page: int
    page_size: int


class ScannerStatusItem(BaseModel):
    timeframe: str
    is_enabled: bool
    is_running: bool
    progress_pct: int
    last_started_at: datetime | None
    next_run_at: datetime | None
    last_scan_status: str | None
    last_tickers_scanned: int
    last_trends_found: int


class UserKpiResponse(BaseModel):
    total_signals_today: int
    uptrend_detected_today: int
    downtrend_detected_today: int
    active_subscribed_pairs: int
    scanner_status: list[ScannerStatusItem]
