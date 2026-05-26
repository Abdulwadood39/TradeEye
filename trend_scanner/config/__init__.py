"""
config/__init__.py — Assembles the iTrade Trend Scanner configuration.

All settings are split across focused modules in this package:
  tickers.py        → what to scan (DEFAULT_TICKERS, STOCKS_INDEX, FOREX_TICKERS …)
  run.py            → how to run (mode, workers, intervals, verbosity)
  signals.py        → signal thresholds (slope, ADX, MK, pivots, channel)
  vetoes.py         → veto gate thresholds (R², Kaufman ER, ATR, body ratio, EMA)
  notifications.py  → alert channels (Telegram, Discord ×3)
  misc.py           → data fetching, charting, VLM, logging

To change any setting, edit the relevant module — no TOML, no CLI flags needed.
The only CLI argument that remains is --tickers (see main.py).

All existing code imports stay unchanged:
  from trend_scanner.config import CFG, DEFAULT_TICKERS, YFINANCE_TO_CCXT
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Sub-module imports ─────────────────────────────────────────────────────────
from trend_scanner.config.tickers import (
    DEFAULT_TICKERS,
    YFINANCE_TO_CCXT,
    STOCKS_INDEX,
    FOREX_TICKERS,
    CRYPTO_TICKERS,
    COMMODITY_TICKERS,
)
from trend_scanner.config.run import RunConfig, RunOnceConfig
from trend_scanner.config.signals import TrendConfig
from trend_scanner.config.vetoes import VetoConfig
from trend_scanner.config.notifications import (
    NotificationsConfig,
    TelegramConfig,
    DiscordConfig,
    DiscordVetosConfig,
    DiscordNoTrendConfig,
)
from trend_scanner.config.misc import DataConfig, ChartConfig, VLMConfig, AlertConfig


# ── Master config dataclass ────────────────────────────────────────────────────

@dataclass
class ScannerConfig:
    """Single config object injected as CFG throughout the codebase."""
    run:           RunConfig           = field(default_factory=RunConfig)
    data:          DataConfig          = field(default_factory=DataConfig)
    trend:         TrendConfig         = field(default_factory=TrendConfig)
    vetoes:        VetoConfig          = field(default_factory=VetoConfig)
    chart:         ChartConfig         = field(default_factory=ChartConfig)
    vlm:           VLMConfig           = field(default_factory=VLMConfig)
    alerts:        AlertConfig         = field(default_factory=AlertConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)


# ── Global singleton ────────────────────────────────────────────────────────────
# All modules do:  from trend_scanner.config import CFG

CFG = ScannerConfig()


# ── Public API (keeps all existing imports working) ────────────────────────────

__all__ = [
    "CFG",
    "ScannerConfig",
    # Tickers
    "DEFAULT_TICKERS",
    "YFINANCE_TO_CCXT",
    "STOCKS_INDEX",
    "FOREX_TICKERS",
    "CRYPTO_TICKERS",
    "COMMODITY_TICKERS",
    # Sub-configs (for type hints elsewhere)
    "RunConfig",
    "RunOnceConfig",
    "TrendConfig",
    "VetoConfig",
    "NotificationsConfig",
    "TelegramConfig",
    "DiscordConfig",
    "DiscordVetosConfig",
    "DiscordNoTrendConfig",
    "DataConfig",
    "ChartConfig",
    "VLMConfig",
    "AlertConfig",
]
