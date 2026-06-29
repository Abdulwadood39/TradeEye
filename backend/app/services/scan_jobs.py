from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID


@dataclass
class ScanJobStatus:
    timeframe_id: UUID
    timeframe_code: str
    status: str  # running | failed
    started_at: datetime
    tickers_total: int = 0
    tickers_done: int = 0
    trends_found: int = 0
    error: str | None = None

    @property
    def progress_pct(self) -> int:
        if self.tickers_total <= 0:
            return 0
        return min(100, int(100 * self.tickers_done / self.tickers_total))


_lock = Lock()
_active: dict[UUID, ScanJobStatus] = {}


def get_running_jobs() -> list[ScanJobStatus]:
    with _lock:
        return sorted(_active.values(), key=lambda j: j.started_at, reverse=True)


def is_timeframe_running(timeframe_id: UUID) -> bool:
    with _lock:
        return timeframe_id in _active


def start_job(timeframe_id: UUID, timeframe_code: str, tickers_total: int) -> None:
    with _lock:
        _active[timeframe_id] = ScanJobStatus(
            timeframe_id=timeframe_id,
            timeframe_code=timeframe_code,
            status="running",
            started_at=datetime.now(timezone.utc),
            tickers_total=tickers_total,
        )


def update_progress(
    timeframe_id: UUID,
    *,
    tickers_done: int | None = None,
    trends_found: int | None = None,
) -> None:
    with _lock:
        job = _active.get(timeframe_id)
        if job is None:
            return
        if tickers_done is not None:
            job.tickers_done = tickers_done
        if trends_found is not None:
            job.trends_found = trends_found


def finish_job(timeframe_id: UUID) -> None:
    with _lock:
        _active.pop(timeframe_id, None)


def fail_job(timeframe_id: UUID, error: str) -> None:
    with _lock:
        _active.pop(timeframe_id, None)
