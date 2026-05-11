"""
config.py — Central configuration for the iTrade Agentic Trend Scanner

All tunable parameters live here. Edit thresholds to adjust sensitivity.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Dict
from dotenv import load_dotenv
load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT TICKER LISTS — override at runtime via CLI --tickers
# ─────────────────────────────────────────────────────────────────────────────

FOREX_TICKERS: List[str] = [
    'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCHF=X', 'AUDUSD=X', 'NZDUSD=X', 'USDCAD=X',
    'EURGBP=X', 'EURJPY=X', 'EURCHF=X', 'EURAUD=X', 'EURNZD=X', 'EURCAD=X',
    'GBPJPY=X', 'GBPCHF=X', 'GBPAUD=X', 'GBPCAD=X', 'GBPNZD=X',
    'AUDJPY=X', 'AUDNZD=X', 'AUDCAD=X', 'AUDCHF=X',
    'NZDJPY=X', 'NZDCAD=X', 'NZDCHF=X',
    'CADJPY=X', 'CADCHF=X',
    'CHFJPY=X',
    'EURSEK=X', 'EURNOK=X', 'EURDKK=X',
    'USDSEK=X', 'USDNOK=X', 'USDDKK=X',
    'GBPSEK=X', 'GBPNOK=X',
    'AUDJPY=X', 'EURHKD=X', 'USDSGD=X', 'EURSGD=X', 'SGDJPY=X',
    'USDHKD=X', 'AUDSGD=X', 'CADSGD=X', 'CHFSGD=X', 'NZDSGD=X',
    'EURPLN=X', 'USDPLN=X',
    'EURCZK=X', 'USDCZK=X',
    'EURHUF=X', 'USDHUF=X',
    'USDMXN=X', 'EURMXN=X',
    'USDZAR=X', 'EURZAR=X',
    'USDTRY=X',
    'USDBRL=X',
    'USDKRW=X',
    'USDTHB=X',
    'USDTWD=X',
    'USDILS=X',
    'USDCLP=X'
]

DEFAULT_TICKERS: List[str] = [
    # Stocks
    "AAPL", "NVDA", "TSLA", "MSFT",
    # Crypto (yfinance format — auto-routed to CCXT Binance if CCXT source)
    # "BTC-USD", "ETH-USD", "SOL-USD",
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
    slope_min_bps: float = 0.20   # raised from 0.15 — must show clear directional drift

    # === Signal 2: Mann-Kendall Test ===
    mk_alpha: float = 0.05          # significance level

    # === Signal 3: ADX ===
    adx_period: int = 14
    adx_threshold: float = 25.0     # raised from 20 — requires a stronger established trend

    # === Signal 4: Higher Highs / Higher Lows (or LH/LL) ===
    # Pivot detection order (bars each side)
    pivot_order: int = 5
    # Minimum fraction of pivots that must show HH+HL (or LH+LL) structure
    hh_hl_min_ratio: float = 0.60   # raised from 0.50 — majority must agree

    # === Signal 5: Pivot Regression Channel ===
    # Both high-pivot and low-pivot regression lines must slope same direction
    channel_slope_min_bps: float = 0.20   # raised from 0.15 — consistent with slope_min_bps

    # === Scoring ===
    # Minimum signals that must pass to declare a trend (out of 5)
    min_signals_for_trend: int = 4   # raised from 3 — need stronger consensus

    # Candle window to run signals over (use last N candles of fetched data)
    analysis_window_1h: int = 2500    # 21 trading days
    analysis_window_1m: int = 2500    # ~3.5 intraday hours
    analysis_window: int = 2500      # Fallback


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
    model: str = "gemini-3-flash-preview"    # free tier, vision-capable
    timeout: int = 30                  # seconds
    # Only run VLM when math score >= this (avoid wasting API calls on weak signals)
    min_score_to_verify: int = 4


# ─────────────────────────────────────────────────────────────────────────────
# ALERT / LOGGING PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlertConfig:
    log_dir: str = "trend_scanner/output/logs"
    log_file: str = "trend_log.csv"
    # Print all results (including no-trend one-liners) — off by default (server-friendly)
    print_all: bool = False
    verbose: bool = True
    # Save charts for ALL tickers, not just trending ones — off by default (debug/dev mode)
    save_all_charts: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATIONS / EXTERNAL ALERTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")    # Your Telegram Bot Token
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")        # Your Telegram Chat ID

@dataclass
class DiscordConfig:
    enabled: bool = False
    webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "") # Your Discord Webhook URL

@dataclass
class NotificationsConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)


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
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    watch:   WatchConfig = field(default_factory=WatchConfig)


CFG = ScannerConfig()
