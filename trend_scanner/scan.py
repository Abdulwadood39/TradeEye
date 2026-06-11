"""
scan.py — Reusable single-ticker scan helper for CLI and SaaS backend.
"""
from __future__ import annotations

from typing import Optional

from trend_scanner.config import CFG, ScannerConfig
from trend_scanner.data.fetcher import fetch
from trend_scanner.engine.trend_engine import TrendEngine, TrendResult


def scan_ticker(
    ticker: str,
    timeframe: str,
    n_bars: int,
    config: Optional[ScannerConfig] = None,
    generate_chart_fn=None,
) -> Optional[TrendResult]:
    """
    Fetch OHLCV and analyse one ticker/timeframe combination.

    Parameters
    ----------
    ticker           : yfinance/CCXT symbol
    timeframe        : e.g. '1m', '1h'
    n_bars           : number of candles to fetch and analyse
    config           : optional ScannerConfig override (defaults to CFG)
    generate_chart_fn: optional callable(df, result) -> chart_path

    Returns
    -------
    TrendResult or None when data is unavailable
    """
    cfg = config or CFG
    df = fetch(ticker, timeframe, n_bars)
    if df is None or len(df) < 50:
        return None

    engine = TrendEngine(config=cfg.trend, vetoes_config=cfg.vetoes)
    result = engine.analyze(df, ticker=ticker, timeframe=timeframe)

    if generate_chart_fn and result.is_trending:
        chart_path = generate_chart_fn(df, result)
        if chart_path:
            result.chart_path = chart_path

    return result
