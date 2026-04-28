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

FOREX_TICKERS: List[str] = [
    # Majors
    "EURUSD=X", "USDJPY=X", "GBPUSD=X", "USDCHF=X", "USDCAD=X", "AUDUSD=X", "NZDUSD=X",
    # EUR Crosses
    "EURGBP=X", "EURJPY=X", "EURCHF=X", "EURCAD=X", "EURAUD=X", "EURNZD=X",
    # GBP Crosses
    "GBPJPY=X", "GBPCHF=X", "GBPCAD=X", "GBPAUD=X", "GBPNZD=X",
    # AUD Crosses
    "AUDJPY=X", "AUDCHF=X", "AUDCAD=X", "AUDNZD=X",
    # NZD Crosses
    "NZDJPY=X", "NZDCHF=X", "NZDCAD=X",
    # CAD & CHF Crosses
    "CADJPY=X", "CADCHF=X", "CHFJPY=X",
    # Minor/Exotic USD Crosses
    "USDMXN=X", "USDZAR=X", "USDTRY=X", "USDSEK=X", "USDNOK=X", "USDDKK=X",
    "USDSGD=X", "USDHKD=X", "USDCNH=X", "USDPLN=X", "USDHUF=X", "USDCZK=X",
    "USDINR=X", "USDTHB=X", "USDKRW=X", "USDTWD=X", "USDIDR=X", "USDMYR=X",
    "USDPHP=X", "USDCLP=X", "USDCOP=X", "USDBRL=X", "USDPEN=X", "USDARS=X",
    "USDILS=X",
    # Minor/Exotic EUR Crosses
    "EURMXN=X", "EURZAR=X", "EURTRY=X", "EURSEK=X", "EURNOK=X", "EURDKK=X",
    "EURPLN=X", "EURHUF=X", "EURCZK=X", "EURSGD=X", "EURHKD=X", "EURILS=X",
    # Minor/Exotic GBP Crosses
    "GBPSEK=X", "GBPNOK=X", "GBPDKK=X", "GBPZAR=X", "GBPSGD=X", "GBPHKD=X",
    "GBPTRY=X", "GBPPLN=X",
    # Minor/Exotic AUD & NZD Crosses
    "AUDSGD=X", "AUDHKD=X", "NZDSGD=X",
    # Minor/Exotic CAD & CHF Crosses
    "CADSGD=X", "CADHKD=X", "CHFSGD=X", "CHFHKD=X", "CHFPLN=X", "CHFZAR=X",
    # Additional Asian/Emerging Crosses
    "SGDJPY=X", "HKDJPY=X", "ZARJPY=X", "MXNJPY=X", "TRYJPY=X", "SEKJPY=X",
    "NOKJPY=X", "PLNJPY=X", "SGDHKD=X",
    # CNH and INR Crosses
    "EURCNH=X", "GBPCNH=X", "AUDCNH=X", "NZDCNH=X", "CADCNH=X", "CHFCNH=X",
    "EURINR=X", "GBPINR=X", "AUDINR=X", "JPYINR=X"
]

DEFAULT_TICKERS: List[str] = [
    # Stocks
    "AAPL", "NVDA", "TSLA", "MSFT",
    # Crypto (yfinance format — auto-routed to CCXT Binance if CCXT source)
    "BTC-USD", "ETH-USD", "SOL-USD",
    # Commodities
    "GC=F",   # Gold
    "CL=F",   # Crude Oil
] + FOREX_TICKERS

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

    # Timeframes to scan (yfinance interval strings)
    timeframes: List[str] = field(default_factory=lambda: ["1h", "1m"])

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
    slope_min_bps: float = 0.15

    # === Signal 2: Mann-Kendall Test ===
    mk_alpha: float = 0.05          # significance level

    # === Signal 3: ADX ===
    adx_period: int = 14
    adx_threshold: float = 20.0     # ADX > this = trending market

    # === Signal 4: Higher Highs / Higher Lows (or LH/LL) ===
    # Pivot detection order (bars each side)
    pivot_order: int = 5
    # Minimum fraction of pivots that must show HH+HL (or LH+LL) structure
    hh_hl_min_ratio: float = 0.50

    # === Signal 5: Pivot Regression Channel ===
    # Both high-pivot and low-pivot regression lines must slope same direction
    channel_slope_min_bps: float = 0.15   # normalized, same as slope_min_bps

    # === Scoring ===
    # Minimum signals that must pass to declare a trend (out of 5)
    min_signals_for_trend: int = 3

    # Candle window to run signals over (use last N candles of fetched data)
    analysis_window_1h: int = 2500    # 21 trading days
    analysis_window_1m: int = 2500    # ~3.5 intraday hours
    analysis_window: int = 3000      # Fallback


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
    up_channel: str = "#58a6ff"
    dn_channel: str = "#ff7b72"
    pivot_hi:   str = "#ffa657"
    pivot_lo:   str = "#7ee787"
    slope_line: str = "#d2a8ff"
    signal_ok:  str = "#3fb950"
    signal_fail:str = "#f85149"


# ─────────────────────────────────────────────────────────────────────────────
# VLM (VISUAL LANGUAGE MODEL) PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VLMConfig:
    enabled: bool = False
    model: str = "qwen3.5:4b"
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
