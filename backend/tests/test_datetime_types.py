from datetime import datetime, timedelta, timezone

from backend.app.db.types import UTCDateTime


def test_utc_datetime_marks_naive_results_as_utc():
    col = UTCDateTime()
    naive = datetime(2026, 6, 16, 12, 0, 0)
    aware = col.process_result_value(naive, dialect=None)

    assert aware is not None
    assert aware.tzinfo == timezone.utc
    assert aware.year == 2026


def test_utc_datetime_strips_timezone_on_write():
    col = UTCDateTime()
    aware = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
    stored = col.process_bind_param(aware, dialect=None)

    assert stored is not None
    assert stored.tzinfo is None
    assert stored == datetime(2026, 6, 16, 12, 0, 0)


def test_scheduler_compare_with_mysql_style_naive_datetime():
    col = UTCDateTime()
    now = datetime.now(timezone.utc)
    next_run_at = col.process_result_value(datetime(2026, 6, 17, 12, 0, 0), dialect=None)

    assert next_run_at is not None
    run_at = next_run_at if next_run_at > now else now
    assert run_at.tzinfo == timezone.utc
