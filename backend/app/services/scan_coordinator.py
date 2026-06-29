from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe
from backend.app.db.models.scan import ScanRun, TrendEvent
from backend.app.db.models.user import UserSubscription
from backend.app.db.session import async_session_factory
from backend.app.indicators.registry import get as get_indicator, init_registry
from backend.app.schemas.trend_directions import NOTIFIABLE_TREND_DIRECTIONS, STORABLE_TREND_DIRECTIONS
from backend.app.services.notification_service import NotificationService
from backend.app.services.scan_jobs import fail_job, finish_job, is_timeframe_running, start_job, update_progress
from trend_scanner.charts.generator import generate_chart
from trend_scanner.data.fetcher import fetch
from trend_scanner.data.normalizer import slice_last_n

logger = logging.getLogger(__name__)


@dataclass
class GroupScanInput:
    ticker_id: UUID
    yfinance_symbol: str
    display_name: str
    timeframe_code: str
    indicator_type_id: UUID
    indicator_slug: str
    unique_bars: list[int]
    max_bars: int
    users_by_bars: dict[int, list[UUID]]
    scan_run_id: UUID
    chart_tmp_dir: str


@dataclass
class GroupScanOutput:
    ticker_id: UUID
    indicator_type_id: UUID
    direction: str
    bars_scanned: int
    score: int
    confidence: float
    display_name: str
    yfinance_symbol: str
    matched_user_ids: list[UUID]
    chart_path: str | None


def _process_group(inp: GroupScanInput) -> list[GroupScanOutput]:
    """Fetch once with max_bars, analyse per unique bars value."""
    init_registry()
    df = fetch(inp.yfinance_symbol, inp.timeframe_code, inp.max_bars)
    if df is None or len(df) < 50:
        return []

    outputs: list[GroupScanOutput] = []
    indicator = get_indicator(inp.indicator_slug)

    for bars in sorted(inp.unique_bars):
        sliced = slice_last_n(df, bars)
        if sliced is None or len(sliced) < 50:
            continue

        result = indicator.analyze(
            sliced,
            ticker=inp.yfinance_symbol,
            timeframe=inp.timeframe_code,
            bars=bars,
        )

        chart_path = None
        if result.direction in NOTIFIABLE_TREND_DIRECTIONS and result.raw_result is not None:
            os.makedirs(os.path.join(inp.chart_tmp_dir, str(inp.scan_run_id)), exist_ok=True)
            chart_path = os.path.join(
                inp.chart_tmp_dir,
                str(inp.scan_run_id),
                f"{inp.yfinance_symbol.replace('/', '_')}_{inp.timeframe_code}_{bars}_{uuid.uuid4().hex}.png",
            )
            chart_path = generate_chart(sliced, result.raw_result, timeframe=inp.timeframe_code, output_path=chart_path)

        outputs.append(
            GroupScanOutput(
                ticker_id=inp.ticker_id,
                indicator_type_id=inp.indicator_type_id,
                direction=result.direction,
                bars_scanned=result.bars_scanned,
                score=result.score,
                confidence=result.confidence,
                display_name=inp.display_name,
                yfinance_symbol=inp.yfinance_symbol,
                matched_user_ids=inp.users_by_bars.get(bars, []),
                chart_path=chart_path,
            )
        )

    return outputs


class ScanCoordinator:
    async def run_timeframe_scan(self, timeframe_id: UUID) -> None:
        if is_timeframe_running(timeframe_id):
            logger.warning("Scan for timeframe %s still running; skipping overlap", timeframe_id)
            return

        try:
            await self._execute_scan(timeframe_id)
        except Exception as exc:
            logger.exception("Scan failed for timeframe %s: %s", timeframe_id, exc)
            fail_job(timeframe_id, str(exc))
            raise

    async def _execute_scan(self, timeframe_id: UUID) -> None:
        init_registry()
        settings = get_settings()

        async with async_session_factory() as db:
            tf_result = await db.execute(select(Timeframe).where(Timeframe.id == timeframe_id))
            timeframe = tf_result.scalar_one_or_none()
            if timeframe is None:
                return

            subs_result = await db.execute(
                select(UserSubscription).where(
                    UserSubscription.timeframe_id == timeframe_id,
                    UserSubscription.is_active.is_(True),
                )
            )
            subscriptions = list(subs_result.scalars().all())
            if not subscriptions:
                logger.info("No active subscriptions for timeframe %s", timeframe.code)
                return

            ticker_cache: dict[UUID, Ticker] = {}
            indicator_cache: dict[UUID, IndicatorType] = {}
            for sub in subscriptions:
                if sub.ticker_id not in ticker_cache:
                    ticker_cache[sub.ticker_id] = (
                        await db.execute(select(Ticker).where(Ticker.id == sub.ticker_id))
                    ).scalar_one()
                if sub.indicator_type_id not in indicator_cache:
                    indicator_cache[sub.indicator_type_id] = (
                        await db.execute(select(IndicatorType).where(IndicatorType.id == sub.indicator_type_id))
                    ).scalar_one()

            started_at = datetime.now(timezone.utc)
            scan_run = ScanRun(
                timeframe_id=timeframe_id,
                indicator_type_id=subscriptions[0].indicator_type_id,
                started_at=started_at,
                status="running",
            )
            db.add(scan_run)
            await db.flush()

            groups: dict[tuple, list[UserSubscription]] = defaultdict(list)
            for sub in subscriptions:
                key = (sub.ticker_id, sub.timeframe_id, sub.indicator_type_id)
                groups[key].append(sub)

            scan_inputs: list[GroupScanInput] = []
            for (ticker_id, _, indicator_type_id), group_subs in groups.items():
                ticker = ticker_cache[ticker_id]
                indicator = indicator_cache[indicator_type_id]
                bars_list = [s.bars for s in group_subs]
                users_by_bars: dict[int, list[UUID]] = defaultdict(list)
                for s in group_subs:
                    users_by_bars[s.bars].append(s.user_id)

                scan_inputs.append(
                    GroupScanInput(
                        ticker_id=ticker_id,
                        yfinance_symbol=ticker.yfinance_symbol,
                        display_name=ticker.display_name,
                        timeframe_code=timeframe.code,
                        indicator_type_id=indicator_type_id,
                        indicator_slug=indicator.slug,
                        unique_bars=sorted(set(bars_list)),
                        max_bars=max(bars_list),
                        users_by_bars=dict(users_by_bars),
                        scan_run_id=scan_run.id,
                        chart_tmp_dir=settings.chart_tmp_dir,
                    )
                )

            start_job(timeframe_id, timeframe.code, len(scan_inputs))

            all_outputs: list[GroupScanOutput] = []
            tickers_done = 0
            try:
                with ThreadPoolExecutor(max_workers=settings.scan_workers) as pool:
                    futures = [pool.submit(_process_group, inp) for inp in scan_inputs]
                    for future in as_completed(futures):
                        tickers_done += 1
                        update_progress(timeframe_id, tickers_done=tickers_done)
                        try:
                            all_outputs.extend(future.result())
                        except Exception as exc:
                            logger.error("Group scan failed: %s", exc)

                notify_service = NotificationService(db)
                trends_found = 0

                for output in all_outputs:
                    if output.direction not in STORABLE_TREND_DIRECTIONS:
                        continue

                    event = TrendEvent(
                        scan_run_id=scan_run.id,
                        ticker_id=output.ticker_id,
                        timeframe_id=timeframe_id,
                        indicator_type_id=output.indicator_type_id,
                        direction=output.direction,
                        bars_scanned=output.bars_scanned,
                        score=output.score,
                        confidence=output.confidence,
                        scanned_at=started_at,
                    )
                    db.add(event)
                    await db.flush()

                    if output.direction in NOTIFIABLE_TREND_DIRECTIONS:
                        trends_found += 1
                    chart_path = output.chart_path
                    if output.direction not in NOTIFIABLE_TREND_DIRECTIONS:
                        continue

                    try:
                        for user_id in output.matched_user_ids:
                            await notify_service.send_trend_alert(
                                user_id=user_id,
                                display_name=output.display_name,
                                yfinance_symbol=output.yfinance_symbol,
                                timeframe=timeframe.code,
                                direction=output.direction,
                                score=output.score,
                                confidence=output.confidence,
                                bars_scanned=output.bars_scanned,
                                chart_path=chart_path,
                                ticker_id=output.ticker_id,
                                timeframe_id=timeframe_id,
                                trend_event_id=event.id,
                            )
                    finally:
                        if chart_path and os.path.exists(chart_path):
                            try:
                                os.remove(chart_path)
                            except OSError as exc:
                                logger.warning("Could not delete chart %s: %s", chart_path, exc)

                update_progress(timeframe_id, trends_found=trends_found)
                scan_run.status = "completed"
                scan_run.finished_at = datetime.now(timezone.utc)
                scan_run.tickers_scanned = len(scan_inputs)
                scan_run.trends_found = trends_found
                await db.commit()
                logger.info(
                    "Scan completed for %s: %d tickers, %d trends",
                    timeframe.code,
                    len(scan_inputs),
                    trends_found,
                )
            finally:
                finish_job(timeframe_id)
