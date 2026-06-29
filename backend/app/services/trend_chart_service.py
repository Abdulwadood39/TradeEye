from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import is_admin_test_user
from backend.app.core.config import get_settings
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe
from backend.app.db.models.scan import TrendEvent
from backend.app.db.models.user import User, UserSubscription
from backend.app.indicators.registry import get as get_indicator, init_registry
from backend.app.schemas.trend_directions import is_vetoed_direction, visible_directions_for_user
from trend_scanner.charts.generator import generate_chart
from trend_scanner.data.fetcher import fetch
from trend_scanner.data.normalizer import slice_last_n


class TrendChartNotFoundError(Exception):
    pass


class TrendChartAccessDeniedError(Exception):
    pass


class TrendChartGenerationError(Exception):
    pass


@dataclass(frozen=True)
class TrendChartBuildInput:
    yfinance_symbol: str
    timeframe_code: str
    indicator_slug: str
    bars: int
    direction: str
    chart_tmp_dir: str


async def _user_can_access_event(db: AsyncSession, user: User, event: TrendEvent) -> bool:
    sub = (
        await db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user.id,
                UserSubscription.is_active.is_(True),
                UserSubscription.ticker_id == event.ticker_id,
                UserSubscription.timeframe_id == event.timeframe_id,
                UserSubscription.bars == event.bars_scanned,
            )
        )
    ).scalar_one_or_none()
    return sub is not None


def _prepare_chart_result(result) -> object | None:
    raw = result.raw_result
    if raw is None:
        return None
    if result.direction == "Vetoed_UP":
        raw.direction = "up"
    elif result.direction == "Vetoed_DOWN":
        raw.direction = "down"
    return raw


def build_trend_event_chart(inp: TrendChartBuildInput) -> str:
    init_registry()
    df = fetch(inp.yfinance_symbol, inp.timeframe_code, inp.bars)
    if df is None or len(df) < 50:
        raise TrendChartGenerationError("Insufficient market data for chart")

    sliced = slice_last_n(df, inp.bars)
    if sliced is None or len(sliced) < 50:
        raise TrendChartGenerationError("Insufficient bars for chart")

    indicator = get_indicator(inp.indicator_slug)
    result = indicator.analyze(
        sliced,
        ticker=inp.yfinance_symbol,
        timeframe=inp.timeframe_code,
        bars=inp.bars,
    )
    if result.direction != inp.direction:
        result = result.model_copy(update={"direction": inp.direction})

    chart_result = _prepare_chart_result(result)
    if chart_result is None:
        raise TrendChartGenerationError("Trend analysis produced no chart data")

    os.makedirs(inp.chart_tmp_dir, exist_ok=True)
    output_path = os.path.join(
        inp.chart_tmp_dir,
        f"{inp.yfinance_symbol.replace('/', '_')}_{inp.timeframe_code}_{inp.bars}_{uuid.uuid4().hex}.png",
    )
    path = generate_chart(sliced, chart_result, timeframe=inp.timeframe_code, output_path=output_path)
    if not path:
        raise TrendChartGenerationError("Chart rendering failed")
    return path


async def prepare_trend_event_chart(
    db: AsyncSession,
    *,
    user: User,
    event_id: UUID,
) -> TrendChartBuildInput:
    event = (
        await db.execute(select(TrendEvent).where(TrendEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise TrendChartNotFoundError

    visible = visible_directions_for_user(is_admin_test_user=is_admin_test_user(user))
    if event.direction not in visible:
        raise TrendChartNotFoundError

    if is_vetoed_direction(event.direction) and not is_admin_test_user(user):
        raise TrendChartNotFoundError

    if not await _user_can_access_event(db, user, event):
        raise TrendChartAccessDeniedError

    ticker = (
        await db.execute(select(Ticker).where(Ticker.id == event.ticker_id))
    ).scalar_one()
    timeframe = (
        await db.execute(select(Timeframe).where(Timeframe.id == event.timeframe_id))
    ).scalar_one()
    indicator = (
        await db.execute(select(IndicatorType).where(IndicatorType.id == event.indicator_type_id))
    ).scalar_one()

    settings = get_settings()
    return TrendChartBuildInput(
        yfinance_symbol=ticker.yfinance_symbol,
        timeframe_code=timeframe.code,
        indicator_slug=indicator.slug,
        bars=event.bars_scanned,
        direction=event.direction,
        chart_tmp_dir=settings.chart_tmp_dir,
    )
