"""
config.py — Central configuration for the iTrade Agentic Trend Scanner

All tunable parameters live here. Edit thresholds to adjust sensitivity.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT TICKER LISTS — override at runtime via CLI --tickers
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TICKERS: List[str] = [
    # Stocks
    "AAPL", "NVDA", "TSLA", "MSFT",
    # Crypto (yfinance format — auto-routed to CCXT Binance if CCXT source)
    "BTC-USD", "ETH-USD", "SOL-USD",
    # Commodities
    "GC=F",   # Gold
    "CL=F",   # Crude Oil
]

# Map yfinance-style crypto tickers → CCXT symbol (BTC-USD → BTC/USDT)
YFINANCE_TO_CCXT: Dict[str, str] = {
    "BTC-USD":  "BTC/USDT",
    "ETH-USD":  "ETH/USDT",
    "SOL-USD":  "SOL/USDT",
    "BNB-USD":  "BNB/USDT",
    "XRP-USD":  "XRP/USDT",
    "ADA-USD":  "ADA/USDT",
    "DOGE-USD": "DOGE/USDT",
    "AVAX-USD": "AVAX/USDT",
    "DOT-USD":  "DOT/USDT",
    "MATIC-USD":"MATIC/USDT",
    "LINK-USD": "LINK/USDT",
    "LTC-USD":  "LTC/USDT",
    "UNI-USD":  "UNI/USDT",
    "ATOM-USD": "ATOM/USDT",
    "XLM-USD":  "XLM/USDT",
}


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCH PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataConfig:
    # How many candles to analyse per timeframe
    n_candles: int = 3000

    # Timeframes to scan — 1h for macro trend, 1m for intraday confirmation
    timeframes: List[str] = field(default_factory=lambda: ["1h", "1m"])

    # For 1m: how many 1-minute candles to fetch (2000 ≈ ~33 hrs crypto / ~5 trading days stocks)
    n_candles_1m: int = 3000

    # yfinance fetch periods
    period_1h: str = "2y"      # max supported by Yahoo Finance
    period_1d: str = "5y"

    # CCXT exchange (no API key needed for public market data)
    ccxt_exchange: str = "binance"

    # Seconds between retries on fetch error
    retry_delay: float = 2.0
    max_retries: int = 3

    # Rate-limit sleep between tickers (seconds)
    ticker_sleep: float = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# TREND ENGINE PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrendConfig:
    # === Signal 1: Linear Regression Slope ===
    # Minimum normalised slope (basis points per candle) to count as trending
    slope_min_bps: float = 0.3

    # === Signal 2: Mann-Kendall Test ===
    mk_alpha: float = 0.05          # significance level

    # === Signal 3: ADX ===
    adx_period: int = 14
    adx_threshold: float = 20.0     # ADX > this = trending market

    # === Signal 4: Higher Highs / Higher Lows (or LH/LL) ===
    # Pivot detection order (bars each side)
    pivot_order: int = 5
    # Minimum fraction of pivots that must show HH+HL (or LH+LL) structure
    hh_hl_min_ratio: float = 0.60

    # === Signal 5: Pivot Regression Channel ===
    # Both high-pivot and low-pivot regression lines must slope same direction
    channel_slope_min_bps: float = 0.1   # normalized, same as slope_min_bps

    # === VETO Signal A: R-squared Linearity Gate ===
    # R² of close prices vs regression line — low R² = noisy/sideways, not a clean trend
    # Must exceed this threshold for a trend to be confirmed (hard veto)
    r2_min_threshold: float = 0.35       # 0.0–1.0; strong trends often reach 0.5–0.8

    # === VETO Signal B: ATR Consolidation Filter ===
    # Ratio of net directional move to (ATR × n_candles). Low ratio = sideways chop.
    # net_move / (atr × window) must exceed this for a trend to be valid
    atr_move_ratio_min: float = 0.08     # markets moving less than 8% of potential range = sideways
    atr_period: int = 14

    # === Signal 6: Dynamic Trendline Touch Validator ===
    # Ascending support (up) or descending resistance (down) must have ≥ N distinct pivot touches
    trendline_min_touches: int = 3
    # Max % distance from trendline for a bar to count as a "touch"
    trendline_touch_pct: float = 0.5     # within 0.5% of the trendline price

    # === Scoring ===
    # Minimum core signals (1–5) that must pass — vetoes are checked separately
    min_signals_for_trend: int = 3

    # Candle window to run signals over (use last N candles of fetched data)
    analysis_window: int = 2000

    # Timeframe-specific analysis windows
    analysis_window_1m: int = 500        # 1m: use last 500 candles for signals (≈8hrs)
    analysis_window_1h: int = 2000       # 1h: use last 2000 candles


# ─────────────────────────────────────────────────────────────────────────────
# CHART PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChartConfig:
    output_dir: str = "trend_scanner/output/charts"
    dpi: int = 150
    figsize_1h: tuple = (20, 9)
    figsize_1m: tuple = (18, 7)

    # How many candles to show before trend start on the overview chart
    overview_candles: int = 2000   # show the full analysis window

    # Dark theme colours (GitHub-style)
    bg:         str = "#0d1117"
    panel:      str = "#161b22"
    grid:       str = "#21262d"
    text:       str = "#e6edf3"
    subtext:    str = "#8b949e"
    bull:       str = "#3fb950"
    bear:       str = "#f85149"
    up_channel:       str = "#58a6ff"
    dn_channel:       str = "#ff7b72"
    pivot_hi:         str = "#ffa657"
    pivot_lo:         str = "#7ee787"
    slope_line:       str = "#d2a8ff"
    signal_ok:        str = "#3fb950"
    signal_fail:      str = "#f85149"
    trendline_up:     str = "#00d4aa"   # Ascending support trendline
    trendline_dn:     str = "#ff6b6b"   # Descending resistance trendline
    trendline_touch:  str = "#ffd700"   # Touch point markers
    consolidation:    str = "#8b949e"   # Sideways / no-trend colour


# ─────────────────────────────────────────────────────────────────────────────
# VLM (VISUAL LANGUAGE MODEL) PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VLMConfig:
    enabled: bool = False
    model: str = "qwen2.5vl:7b"
    timeout: int = 120       # seconds to wait for Ollama response
    # Only run VLM when math score >= this (avoid wasting time on weak signals)
    min_score_to_verify: int = 3


# ─────────────────────────────────────────────────────────────────────────────
# ALERT / LOGGING PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlertConfig:
    log_dir: str = "trend_scanner/output/logs"
    log_file: str = "trend_log.csv"
    # Print all results or only trends
    print_all: bool = False
    verbose: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# WATCH MODE (continuous scanning)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WatchConfig:
    enabled: bool = False
    interval_minutes: int = 60     # re-scan every N minutes


# ─────────────────────────────────────────────────────────────────────────────
# MASTER CONFIG SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScannerConfig:
    data:    DataConfig  = field(default_factory=DataConfig)
    trend:   TrendConfig = field(default_factory=TrendConfig)
    chart:   ChartConfig = field(default_factory=ChartConfig)
    vlm:     VLMConfig   = field(default_factory=VLMConfig)
    alerts:  AlertConfig = field(default_factory=AlertConfig)
    watch:   WatchConfig = field(default_factory=WatchConfig)


CFG = ScannerConfig()
