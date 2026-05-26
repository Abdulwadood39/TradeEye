"""
config/misc.py — Data fetching, charting, VLM, and logging settings.

These are operational settings you rarely need to change.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataConfig:
    ccxt_exchange: str = "binance"   # exchange used for crypto OHLCV
    retry_delay: float = 2.0         # seconds between retries on fetch error
    max_retries: int = 3
    ticker_sleep: float = 0.5        # rate-limit sleep between tickers (seconds)


# ─────────────────────────────────────────────────────────────────────────────
# CHARTING
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChartConfig:
    output_dir: str = "trend_scanner/output/charts"
    dpi: int = 150

    figsize_default: tuple = (20, 9)
    figsize_per_tf: Dict[str, tuple] = field(default_factory=lambda: {
        "1m":  (18, 7),
        "5m":  (18, 7),
        "15m": (18, 7),
        "30m": (18, 8),
        "1h":  (20, 9),
        "4h":  (20, 9),
        "1d":  (20, 9),
    })
    overview_candles: int = 2000

    # Dark GitHub-style colour palette
    bg:          str = "#0d1117"
    panel:       str = "#161b22"
    grid:        str = "#21262d"
    text:        str = "#e6edf3"
    subtext:     str = "#8b949e"
    bull:        str = "#3fb950"
    bear:        str = "#f85149"
    up_channel:  str = "#58a6ff"
    dn_channel:  str = "#ff7b72"
    pivot_hi:    str = "#ffa657"
    pivot_lo:    str = "#7ee787"
    slope_line:  str = "#d2a8ff"
    signal_ok:   str = "#3fb950"
    signal_fail: str = "#f85149"

    def figsize_for(self, timeframe: str) -> tuple:
        return self.figsize_per_tf.get(timeframe, self.figsize_default)


# ─────────────────────────────────────────────────────────────────────────────
# VLM (VISUAL LANGUAGE MODEL) — Gemini chart verification
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VLMConfig:
    # Set to True to enable Gemini chart verification (requires GEMINI_API_KEY)
    enabled: bool = False
    model: str = "gemini-3-flash-preview"
    timeout: int = 30
    # Only verify tickers that scored >= this (avoids wasting API calls)
    min_score_to_verify: int = 4


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING / TERMINAL OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlertConfig:
    log_dir: str = "trend_scanner/output/logs"
    log_file: str = "trend_log.csv"
    # These mirror the RunConfig flags and are synced at scan start.
    print_all: bool = False
    verbose: bool = True
    save_all_charts: bool = True
