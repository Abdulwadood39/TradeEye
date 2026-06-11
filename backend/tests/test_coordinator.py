from unittest.mock import MagicMock, patch
from uuid import uuid4

import pandas as pd

from backend.app.services.scan_coordinator import GroupScanInput, _process_group


def _make_df(n: int) -> pd.DataFrame:
    import numpy as np
    return pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": np.linspace(100, 110, n),
        "high": np.linspace(101, 111, n),
        "low": np.linspace(99, 109, n),
        "close": np.linspace(100, 120, n),
        "volume": np.ones(n) * 1000,
    })


@patch("backend.app.services.scan_coordinator.generate_chart")
@patch("backend.app.services.scan_coordinator.fetch")
def test_bars_exact_user_matching(mock_fetch, mock_chart, chart_tmp_dir):
    mock_fetch.return_value = _make_df(2500)
    mock_chart.return_value = None

    user_a, user_b = uuid4(), uuid4()
    inp = GroupScanInput(
        ticker_id=uuid4(),
        yfinance_symbol="GC=F",
        display_name="Gold",
        timeframe_code="1m",
        indicator_type_id=uuid4(),
        indicator_slug="continuous_trend",
        unique_bars=[1500, 2500],
        max_bars=2500,
        users_by_bars={1500: [user_a], 2500: [user_b]},
        scan_run_id=uuid4(),
        chart_tmp_dir=chart_tmp_dir,
    )

    with patch("backend.app.services.scan_coordinator.get_indicator") as mock_get:
        indicator = MagicMock()
        indicator.analyze.side_effect = [
            MagicMock(
                direction="UP", score=4, confidence=0.8, bars_scanned=1500,
                raw_result=MagicMock(is_trending=True),
            ),
            MagicMock(
                direction="DOWN", score=4, confidence=0.7, bars_scanned=2500,
                raw_result=MagicMock(is_trending=True),
            ),
        ]
        mock_get.return_value = indicator

        outputs = _process_group(inp)

    assert len(outputs) == 2
    assert outputs[0].bars_scanned == 1500
    assert outputs[0].matched_user_ids == [user_a]
    assert outputs[0].direction == "UP"
    assert outputs[1].bars_scanned == 2500
    assert outputs[1].matched_user_ids == [user_b]
    assert outputs[1].direction == "DOWN"
    mock_fetch.assert_called_once_with("GC=F", "1m", 2500)
    assert indicator.analyze.call_count == 2


@patch("backend.app.services.scan_coordinator.fetch")
def test_single_fetch_max_bars(mock_fetch, chart_tmp_dir):
    mock_fetch.return_value = _make_df(2000)
    inp = GroupScanInput(
        ticker_id=uuid4(),
        yfinance_symbol="AAPL",
        display_name="Apple",
        timeframe_code="1h",
        indicator_type_id=uuid4(),
        indicator_slug="continuous_trend",
        unique_bars=[500, 1000],
        max_bars=1000,
        users_by_bars={500: [uuid4()], 1000: [uuid4()]},
        scan_run_id=uuid4(),
        chart_tmp_dir=chart_tmp_dir,
    )

    with patch("backend.app.services.scan_coordinator.get_indicator") as mock_get:
        indicator = MagicMock()
        indicator.analyze.return_value = MagicMock(
            direction="NONE", score=0, confidence=0.0, bars_scanned=500, raw_result=None
        )
        mock_get.return_value = indicator
        _process_group(inp)

    mock_fetch.assert_called_once_with("AAPL", "1h", 1000)
