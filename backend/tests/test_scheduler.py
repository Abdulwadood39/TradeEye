import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.services import scan_scheduler


@pytest.mark.asyncio
async def test_schedule_next_registers_job():
    tf_id = uuid4()
    run_at = datetime.now(timezone.utc) + timedelta(hours=24)
    scan_scheduler.start_scheduler()
    try:
        scan_scheduler._schedule_next(tf_id, run_at, "1h")
        job = scan_scheduler.scheduler.get_job(scan_scheduler._job_ids[tf_id])
        assert job is not None
        assert job.id == f"scan_{tf_id}"
    finally:
        scan_scheduler.shutdown_scheduler()
