"""
config/run.py — Controls HOW the scanner runs.

Edit this file to change:
  - Scan mode (continuous loops vs one-shot)
  - Which timeframe loops to run and how often
  - Worker thread count, verbosity, chart saving
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RunOnceConfig:
    """Settings used only when mode = 'once'."""
    # Timeframes scanned when mode = "once", then the process exits.
    timeframes: List[str] = field(default_factory=lambda: ["1h", "1m", "5m"])


@dataclass
class RunConfig:
    # ── Scan mode ──────────────────────────────────────────────────────────────
    # "continuous"  → starts one background loop per entry in `intervals`
    # "once"        → scans each timeframe in `once.timeframes` then exits
    mode: str = "continuous"

    # ── Parallel workers ───────────────────────────────────────────────────────
    workers: int = 32          # concurrent fetch+analyse threads per scan batch

    # ── Output verbosity ───────────────────────────────────────────────────────
    verbose: bool = True       # print full signal breakdown for trending results
    print_all: bool = False    # also print one-liners for non-trend tickers
    save_all_charts: bool = True  # save charts for ALL tickers (not just trends)

    # ── Timeframe scan loops (mode = "continuous") ─────────────────────────────
    # Format: { "timeframe": repeat_interval_in_minutes }
    # Add any new timeframe here — no code changes needed anywhere else.
    intervals: Dict[str, int] = field(default_factory=lambda: {
        "1h":  1440,  # repeat every 24 h
        "1m":  180,   # repeat every  3 h
        # "5m":  900,   # repeat every 15 h
        # "15m": 1440,  # repeat every 24 h
        # "30m": 1440,  # repeat every 24 h
        # "4h":  1440,  # repeat every 24 h
        # "1d":  43200, # repeat every 30 d
    })

    # ── One-shot settings (mode = "once") ─────────────────────────────────────
    once: RunOnceConfig = field(default_factory=RunOnceConfig)
