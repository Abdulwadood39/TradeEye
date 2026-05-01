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
    'EURUSD=X', 'GBPUSD=X', 'AUDUSD=X', 'NZDUSD=X', 'USDCAD=X', 'USDCHF=X', 'USDJPY=X', 'EURGBP=X', 'EURAUD=X', 'EURNZD=X',
    'EURCAD=X', 'EURCHF=X', 'EURJPY=X', 'GBPAUD=X', 'GBPNZD=X', 'GBPCAD=X', 'GBPCHF=X', 'GBPJPY=X', 'AUDNZD=X', 'AUDCAD=X',
    'AUDCHF=X', 'AUDJPY=X', 'NZDCAD=X', 'NZDCHF=X', 'NZDJPY=X', 'CADCHF=X', 'CADJPY=X', 'CHFJPY=X', 'USDHKD=X', 'USDSGD=X',
    'USDZAR=X', 'USDTRY=X', 'USDMXN=X', 'USDNOK=X', 'USDSEK=X', 'USDDKK=X', 'USDPLN=X', 'USDHUF=X', 'USDCZK=X', 'USDTHB=X',
    'USDKRW=X', 'USDIDR=X', 'USDPHP=X', 'USDTWD=X', 'USDMYR=X', 'USDVND=X', 'USDBRL=X', 'USDCLP=X', 'USDCOP=X', 'USDPEN=X',
    'USDARS=X', 'USDUYU=X', 'USDISK=X', 'USDRON=X', 'USDBGN=X', 'USDAED=X', 'USDSAR=X', 'USDQAR=X', 'USDKWD=X', 'USDOMR=X',
    'USDBHD=X', 'USDJOD=X', 'USDEGP=X', 'USDNGN=X', 'USDKES=X', 'USDGHS=X', 'USDTZS=X', 'USDUGX=X', 'USDMAD=X', 'USDTND=X',
    'USDXOF=X', 'USDXAF=X', 'USDCRC=X', 'USDPAB=X', 'USDDOP=X', 'USDJMD=X', 'USDBBD=X', 'USDBSD=X', 'USDTTD=X', 'USDBZD=X',
    'EURSGD=X', 'EURHKD=X', 'EURZAR=X', 'EURTRY=X', 'EURMXN=X', 'EURNOK=X', 'EURSEK=X', 'EURDKK=X', 'EURPLN=X', 'EURHUF=X',
    'EURCZK=X', 'EURTHB=X', 'EURKRW=X', 'EURIDR=X', 'EURPHP=X', 'EURTWD=X', 'EURMYR=X', 'EURVND=X', 'EURBRL=X', 'EURCLP=X',
    'EURCOP=X', 'EURPEN=X', 'EURARS=X', 'EURUYU=X', 'EURISK=X', 'EURRON=X', 'EURBGN=X', 'EURAED=X', 'EURSAR=X', 'EURQAR=X',
    'EURKWD=X', 'EUROMR=X', 'EURBHD=X', 'EURJOD=X', 'EUREGP=X', 'EURNGN=X', 'EURKES=X', 'EURGHS=X', 'EURTZS=X', 'EURUGX=X',
    'GBPSGD=X', 'GBPHKD=X', 'GBPZAR=X', 'GBPTRY=X', 'GBPMXN=X', 'GBPNOK=X', 'GBPSEK=X', 'GBPDKK=X', 'GBPPLN=X', 'GBPHUF=X',
    'GBPCZK=X', 'GBPTHB=X', 'GBPKRW=X', 'GBPIDR=X', 'GBPPHP=X', 'GBPTWD=X', 'GBPMYR=X', 'GBPVND=X', 'GBPBRL=X', 'GBPCLP=X',
    'GBPCOP=X', 'GBPPEN=X', 'GBPARS=X', 'GBPUYU=X', 'GBPISK=X', 'GBPRON=X', 'GBPBGN=X', 'GBPAED=X', 'GBPSAR=X', 'GBPQAR=X',
    'GBPKWD=X', 'GBPOMR=X', 'GBPBHD=X', 'GBPJOD=X', 'GBPEGP=X', 'GBPNGN=X', 'GBPKES=X', 'GBPGHS=X', 'GBPTZS=X', 'GBPUGX=X',
    'AUDSGD=X', 'AUDHKD=X', 'AUDZAR=X', 'AUDTRY=X', 'AUDMXN=X', 'AUDNOK=X', 'AUDSEK=X', 'AUDDKK=X', 'AUDPLN=X', 'AUDHUF=X',
    'AUDCZK=X', 'AUDTHB=X', 'AUDKRW=X', 'AUDIDR=X', 'AUDPHP=X', 'AUDTWD=X', 'AUDMYR=X', 'AUDVND=X', 'AUDBRL=X', 'AUDCLP=X',
    'AUDCOP=X', 'AUDPEN=X', 'AUDARS=X', 'AUDUYU=X', 'AUDISK=X', 'AUDRON=X', 'AUDBGN=X', 'AUDAED=X', 'AUDSAR=X', 'AUDQAR=X',
    'AUDKWD=X', 'AUDOMR=X', 'AUDBHD=X', 'AUDJOD=X', 'AUDEGP=X', 'AUDNGN=X', 'AUDKES=X', 'AUDGHS=X', 'AUDTZS=X', 'AUDUGX=X',
    'NZDSGD=X', 'NZDHKD=X', 'NZDZAR=X', 'NZDTRY=X', 'NZDMXN=X', 'NZDNOK=X', 'NZDSEK=X', 'NZDDKK=X', 'NZDPLN=X', 'NZDHUF=X',
    'NZDCZK=X', 'NZDTHB=X', 'NZDKRW=X', 'NZDIDR=X', 'NZDPHP=X', 'NZDTWD=X', 'NZDMYR=X', 'NZDVND=X', 'NZDBRL=X', 'NZDCLP=X',
    'NZDCOP=X', 'NZDPEN=X', 'NZDARS=X', 'NZDUYU=X', 'NZDISK=X', 'NZDRON=X', 'NZDBGN=X', 'NZDAED=X', 'NZDSAR=X', 'NZDQAR=X',
    'NZDKWD=X', 'NZDOMR=X', 'NZDBHD=X', 'NZDJOD=X', 'NZDEGP=X', 'NZDNGN=X', 'NZDKES=X', 'NZDGHS=X', 'NZDTZS=X', 'NZDUGX=X',
    'CADSGD=X', 'CADHKD=X', 'CADZAR=X', 'CADTRY=X', 'CADMXN=X', 'CADNOK=X', 'CADSEK=X', 'CADDKK=X', 'CADPLN=X', 'CADHUF=X',
    'CADCZK=X', 'CADTHB=X', 'CADKRW=X', 'CADIDR=X', 'CADPHP=X', 'CADTWD=X', 'CADMYR=X', 'CADVND=X', 'CADBRL=X', 'CADCLP=X',
    'CADCOP=X', 'CADPEN=X', 'CADARS=X', 'CADUYU=X', 'CADISK=X', 'CADRON=X', 'CADBGN=X', 'CADAED=X', 'CADSAR=X', 'CADQAR=X',
    'CADKWD=X', 'CADOMR=X', 'CADBHD=X', 'CADJOD=X', 'CADEGP=X', 'CADNGN=X', 'CADKES=X', 'CADGHS=X', 'CADTZS=X', 'CADUGX=X',
    'CHFSGD=X', 'CHFHKD=X', 'CHFZAR=X', 'CHFTRY=X', 'CHFMXN=X', 'CHFNOK=X', 'CHFSEK=X', 'CHFDKK=X', 'CHFPLN=X', 'CHFHUF=X',
    'CHFCZK=X', 'CHFTHB=X', 'CHFKRW=X', 'CHFIDR=X', 'CHFPHP=X', 'CHFTWD=X', 'CHFMYR=X', 'CHFVND=X', 'CHFBRL=X', 'CHFCLP=X',
    'CHFCOP=X', 'CHFPEN=X', 'CHFARS=X', 'CHFUYU=X', 'CHFISK=X', 'CHFRON=X', 'CHFBGN=X', 'CHFAED=X', 'CHFSAR=X', 'CHFQAR=X',
    'CHFKWD=X', 'CHFOMR=X', 'CHFBHD=X', 'CHFJOD=X', 'CHFEGP=X', 'CHFNGN=X', 'CHFKES=X', 'CHFGHS=X', 'CHFTZS=X', 'CHFUGX=X',
    'JPYSGD=X', 'JPYHKD=X', 'JPYZAR=X', 'JPYTRY=X', 'JPYMXN=X', 'JPYNOK=X', 'JPYSEK=X', 'JPYDKK=X', 'JPYPLN=X', 'JPYHUF=X',
    'JPYCZK=X', 'JPYTHB=X', 'JPYKRW=X', 'JPYIDR=X', 'JPYPHP=X', 'JPYTWD=X', 'JPYMYR=X', 'JPYVND=X', 'JPYBRL=X', 'JPYCLP=X',
    'JPYCOP=X', 'JPYPEN=X', 'JPYARS=X', 'JPYUYU=X', 'JPYISK=X', 'JPYRON=X', 'JPYBGN=X', 'JPYAED=X', 'JPYSAR=X', 'JPYQAR=X',
    'JPYKWD=X', 'JPYOMR=X', 'JPYBHD=X', 'JPYJOD=X', 'JPYEGP=X', 'JPYNGN=X', 'JPYKES=X', 'JPYGHS=X', 'JPYTZS=X', 'JPYUGX=X',
    'SGDHKD=X', 'SGDZAR=X', 'SGDTRY=X', 'SGDMXN=X', 'SGDNOK=X', 'SGDSEK=X', 'SGDDKK=X', 'SGDPLN=X', 'SGDHUF=X', 'SGDCZK=X',
    'SGDTHB=X', 'SGDKRW=X', 'SGDIDR=X', 'SGDPHP=X', 'SGDTWD=X', 'SGDMYR=X', 'SGDVND=X', 'SGDBRL=X', 'SGDCLP=X', 'SGDCOP=X',
    'SGDPEN=X', 'SGDARS=X', 'SGDUYU=X', 'SGDISK=X', 'SGDRON=X', 'SGDBGN=X', 'SGDAED=X', 'SGDSAR=X', 'SGDQAR=X', 'SGDKWD=X',
    'SGDOMR=X', 'SGDBHD=X', 'SGDJOD=X', 'SGDEGP=X', 'SGDNGN=X', 'SGDKES=X', 'SGDGHS=X', 'SGDTZS=X', 'SGDUGX=X', 'HKDZAR=X',
    'HKDTRY=X', 'HKDMXN=X', 'HKDNOK=X', 'HKDSEK=X', 'HKDDKK=X', 'HKDPLN=X', 'HKDHUF=X', 'HKDCZK=X', 'HKDTHB=X', 'HKDKRW=X',
    'HKDIDR=X', 'HKDPHP=X', 'HKDTWD=X', 'HKDMYR=X', 'HKDVND=X', 'HKDBRL=X', 'HKDCLP=X', 'HKDCOP=X', 'HKDPEN=X', 'HKDARS=X',
    'HKDUYU=X', 'HKDISK=X', 'HKDRON=X', 'HKDBGN=X', 'HKDAED=X', 'HKDSAR=X', 'HKDQAR=X', 'HKDKWD=X', 'HKDOMR=X', 'HKDBHD=X',
    'HKDJOD=X', 'HKDEGP=X', 'HKDNGN=X', 'HKDKES=X', 'HKDGHS=X', 'HKDTZS=X', 'HKDUGX=X', 'ZARTRY=X', 'ZARMXN=X', 'ZARNOK=X',
    'ZARSEK=X', 'ZARDKK=X', 'ZARPLN=X', 'ZARHUF=X', 'ZARCZK=X', 'ZARTHB=X', 'ZARKRW=X', 'ZARIDR=X', 'ZARPHP=X', 'ZARTWD=X',
    'ZARMYR=X', 'ZARVND=X', 'ZARBRL=X', 'ZARCLP=X', 'ZARCOP=X', 'ZARPEN=X', 'ZARARS=X', 'ZARUYU=X', 'ZARISK=X', 'ZARRON=X'
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
class NotificationsConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


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
