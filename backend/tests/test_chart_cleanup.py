import os

from backend.app.main import _sweep_orphan_charts


def test_orphan_chart_sweep(tmp_path):
    chart_dir = tmp_path / "charts"
    chart_dir.mkdir()
    old_file = chart_dir / "old.png"
    old_file.write_bytes(b"png")
    old_ts = os.path.getmtime(old_file)
    os.utime(old_file, (old_ts - 7200, old_ts - 7200))

    new_file = chart_dir / "new.png"
    new_file.write_bytes(b"png")

    _sweep_orphan_charts(str(chart_dir), max_age_seconds=3600)

    assert not old_file.exists()
    assert new_file.exists()
