from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from backend.app.db.models.catalog import Timeframe, TimeframeScanSchedule
from backend.app.db.session import async_session_factory
from backend.app.services.scan_coordinator import ScanCoordinator

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
coordinator = ScanCoordinator()
_job_ids: Dict[UUID, str] = {}


async def _fire_scan(timeframe_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        result = await db.execute(
            select(TimeframeScanSchedule).where(TimeframeScanSchedule.timeframe_id == timeframe_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None or not schedule.is_enabled:
            return

        schedule.last_started_at = now
        schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
        await db.commit()
        next_run = schedule.next_run_at

    _schedule_next(timeframe_id, next_run)
    asyncio.create_task(coordinator.run_timeframe_scan(timeframe_id))


def _schedule_next(timeframe_id: UUID, run_at: datetime) -> None:
    job_id = _job_ids.get(timeframe_id, f"scan_{timeframe_id}")
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _fire_scan,
        trigger="date",
        run_date=run_at,
        args=[timeframe_id],
        id=job_id,
        replace_existing=True,
    )
    _job_ids[timeframe_id] = job_id
    logger.info("Scheduled next scan for timeframe %s at %s", timeframe_id, run_at.isoformat())


async def load_schedules() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(TimeframeScanSchedule, Timeframe)
            .join(Timeframe, TimeframeScanSchedule.timeframe_id == Timeframe.id)
            .where(TimeframeScanSchedule.is_enabled.is_(True))
        )
        rows = result.all()

    now = datetime.now(timezone.utc)
    for schedule, tf in rows:
        run_at = schedule.next_run_at if schedule.next_run_at and schedule.next_run_at > now else now
        _schedule_next(schedule.timeframe_id, run_at)
        logger.info("Loaded schedule for %s: every %d min", tf.code, schedule.interval_minutes)


async def reload_schedule(timeframe_id: UUID) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(TimeframeScanSchedule).where(TimeframeScanSchedule.timeframe_id == timeframe_id)
        )
        schedule = result.scalar_one_or_none()

    if schedule is None or not schedule.is_enabled:
        job_id = _job_ids.pop(timeframe_id, None)
        if job_id and scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        return

    now = datetime.now(timezone.utc)
    run_at = schedule.next_run_at if schedule.next_run_at and schedule.next_run_at > now else now
    _schedule_next(timeframe_id, run_at)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
