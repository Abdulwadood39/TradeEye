"""
config/signals.py — The 5 trend-detection signal thresholds.

Edit this file to tune how aggressively the scanner identifies trends.
Higher thresholds = fewer, higher-quality signals.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class TrendConfig:
    # ── Signal 1: Linear Regression Slope ─────────────────────────────────────
    # Minimum slope in basis points per candle for an uptrend/downtrend.
    # Increase to require steeper moves; decrease to catch slower drifts.
    slope_min_bps: float = 0.20

    # ── Signal 2: Mann-Kendall Trend Test ─────────────────────────────────────
    # Significance level (p-value threshold). Lower = stricter.
    mk_alpha: float = 0.05

    # ── Signal 3: ADX ─────────────────────────────────────────────────────────
    adx_period: int = 14
    adx_threshold: float = 25.0
    # Set True to also require ADX to be rising over the last 5 bars.
    # Useful for catching early-stage breakouts; increases false-negative rate.
    adx_require_rising: bool = False

    # ── Signal 4: Market Structure (Higher Highs / Higher Lows) ───────────────
    pivot_order: int = 5           # how many bars each side for swing pivots
    hh_hl_min_ratio: float = 0.55  # fraction of pivots that must be HH+HL (uptrend)

    # ── Signal 5: Pivot Regression Channel ────────────────────────────────────
    channel_slope_min_bps: float = 0.20

    # ── Minimum passing signals to declare a trend ────────────────────────────
    # 4/5 = high confidence.  3/5 = more sensitive but more noise.
    min_signals_for_trend: int = 4

    # ── Candle window per timeframe ────────────────────────────────────────────
    # How many candles are sliced for analysis.
    # Add new timeframes freely — the engine falls back to 2500 for unknown TFs.
    analysis_windows: Dict[str, int] = field(default_factory=lambda: {
        "1m":  2500,
        "5m":  2500,
        "15m": 2500,
        "30m": 2500,
        "1h":  2500,
        "2h":  2500,
        "4h":  2500,
        "1d":  2500,
    })

    def window_for(self, timeframe: str) -> int:
        """Return the analysis candle window for a timeframe (fallback: 2500)."""
        return self.analysis_windows.get(timeframe, 2500)
