from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import is_admin_test_user
from backend.app.db.models.catalog import Timeframe, TimeframeScanSchedule
from backend.app.db.models.scan import ScanRun, TrendEvent
from backend.app.db.models.user import User, UserSubscription
from backend.app.schemas.trend_directions import visible_directions_for_user
from backend.app.services.scan_jobs import get_running_jobs


def _start_of_utc_day() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_user_kpis(db: AsyncSession, user: User) -> dict:
    visible = visible_directions_for_user(is_admin_test_user=is_admin_test_user(user))

    active_pairs = (
        await db.execute(
            select(func.count()).select_from(UserSubscription).where(
                UserSubscription.user_id == user.id,
                UserSubscription.is_active.is_(True),
            )
        )
    ).scalar() or 0

    subs = (
        await db.execute(
            select(
                UserSubscription.ticker_id,
                UserSubscription.timeframe_id,
                UserSubscription.bars,
            ).where(UserSubscription.user_id == user.id, UserSubscription.is_active.is_(True))
        )
    ).all()

    start_of_day = _start_of_utc_day()
    direction_counts = {direction: 0 for direction in visible}
    total_signals_today = 0

    if subs:
        conditions = [
            (TrendEvent.ticker_id == ticker_id)
            & (TrendEvent.timeframe_id == timeframe_id)
            & (TrendEvent.bars_scanned == bars)
            for ticker_id, timeframe_id, bars in subs
        ]
        rows = (
            await db.execute(
                select(TrendEvent.direction, func.count())
                .where(
                    or_(*conditions),
                    TrendEvent.direction.in_(visible),
                    TrendEvent.scanned_at >= start_of_day,
                )
                .group_by(TrendEvent.direction)
            )
        ).all()
        for direction, count in rows:
            direction_counts[direction] = count
            total_signals_today += count

    subscribed_timeframe_ids = {timeframe_id for _, timeframe_id, _ in subs}
    scanner_status = []
    running_by_tf = {job.timeframe_id: job for job in get_running_jobs()}

    if subscribed_timeframe_ids:
        schedule_rows = (
            await db.execute(
                select(TimeframeScanSchedule, Timeframe)
                .join(Timeframe, TimeframeScanSchedule.timeframe_id == Timeframe.id)
                .where(TimeframeScanSchedule.timeframe_id.in_(subscribed_timeframe_ids))
            )
        ).all()

        for schedule, tf in schedule_rows:
            last_run = (
                await db.execute(
                    select(ScanRun)
                    .where(ScanRun.timeframe_id == tf.id)
                    .order_by(ScanRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            running = running_by_tf.get(tf.id)
            scanner_status.append(
                {
                    "timeframe": tf.code,
                    "is_enabled": schedule.is_enabled,
                    "is_running": running is not None,
                    "progress_pct": running.progress_pct if running else 0,
                    "last_started_at": schedule.last_started_at,
                    "next_run_at": schedule.next_run_at,
                    "last_scan_status": last_run.status if last_run else None,
                    "last_tickers_scanned": last_run.tickers_scanned if last_run else 0,
                    "last_trends_found": last_run.trends_found if last_run else 0,
                }
            )

    return {
        "total_signals_today": total_signals_today,
        "uptrend_detected_today": direction_counts.get("UP", 0),
        "downtrend_detected_today": direction_counts.get("DOWN", 0),
        "active_subscribed_pairs": active_pairs,
        "scanner_status": scanner_status,
    }
