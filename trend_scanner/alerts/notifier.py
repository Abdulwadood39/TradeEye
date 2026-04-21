"""
notifier.py — Terminal alerts and CSV logging for trend detections.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from typing import List

from trend_scanner.config import CFG
from trend_scanner.engine.trend_engine import TrendResult


# ─────────────────────────────────────────────────────────────────────────────
# ANSI COLOUR CODES (for terminal)
# ─────────────────────────────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_GREY   = "\033[90m"
_BLUE   = "\033[94m"
_MAGENTA= "\033[95m"


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if _supports_color():
        return f"{code}{text}{_RESET}"
    return text


# ─────────────────────────────────────────────────────────────────────────────
# PRINT ALERTS
# ─────────────────────────────────────────────────────────────────────────────

def print_result(result: TrendResult, verbose: bool = None):
    """
    Print a formatted trend result to the terminal.
    Shows abbreviated info for non-trends, full box for detected trends.
    """
    verbose = verbose if verbose is not None else CFG.alerts.verbose
    is_trend = result.is_trending

    # One-liner for clean no-trend (not veto-killed)
    if not is_trend and not result.veto_killed and not CFG.alerts.print_all:
        print(
            _c(f"  ➡️  {result.ticker:<12} {result.timeframe:<4}", _GREY) +
            _c(f"  NO TREND  ", _GREY) +
            _c(f"score={result.score}/5", _GREY)
        )
        return

    # ── Full alert box ───────────────────────────────────────────────────────
    if result.veto_killed:
        border_color = _YELLOW    # amber = vetoed
    elif result.direction == "up":
        border_color = _GREEN
    elif result.direction == "down":
        border_color = _RED
    else:
        border_color = _GREY

    border = "─" * 64
    print()
    print(_c(border, border_color))

    direction_color = _GREEN if result.direction == "up" else (_RED if result.direction == "down" else _YELLOW)
    print(_c(f"  {result.emoji}  {result.direction_label}", direction_color + _BOLD) +
          _c(f"  ·  {result.ticker}  ·  {result.timeframe}", _BOLD))

    score_bar = "█" * result.score + "░" * (5 - result.score)
    print(_c(f"  Score: [{score_bar}] {result.score}/5  ", _CYAN) +
          _c(f"Confidence: {result.confidence:.0%}", _YELLOW) +
          _c(f"  Candles: {result.candles_analyzed}", _GREY))

    if result.veto_killed:
        print(_c(f"  ⚡ VETOED by: {', '.join(result.vetoes_failed)}", _YELLOW + _BOLD))

    if verbose and result.signals:
        print(_c("  Core Signals:", _BLUE))
        for sig in result.signals:
            icon = "✓" if sig.passed else "✗"
            col  = _GREEN if sig.passed else _GREY
            det  = "  ".join(f"{k}={v}" for k, v in list(sig.detail.items())[:3])
            print(_c(f"    {icon} {sig.name:<28}", col) +
                  _c(f"score={sig.score:.0%}  {det}", _GREY))

    if verbose and result.vetoes:
        print(_c("  Veto Gates:", _MAGENTA))
        for v in result.vetoes:
            icon = "✓" if v.passed else "✗"
            col  = _GREEN if v.passed else _YELLOW
            det  = "  ".join(f"{k}={val}" for k, val in list(v.detail.items())[:2])
            print(_c(f"    {icon} {v.name:<28}", col) +
                  _c(f"{det}", _GREY))

    if result.vlm_verdict:
        vlm_col = _GREEN if "uptrend" in result.vlm_verdict else _RED
        print(_c(f"  🤖 VLM ({CFG.vlm.model}): {result.vlm_verdict}", vlm_col) +
              (f"  conf={result.vlm_confidence:.0%}" if result.vlm_confidence else ""))

    chart_path = result.chart_1h_path or result.chart_1m_path
    if chart_path:
        print(_c(f"  📊 Chart: {chart_path}", _CYAN))

    print(_c(border, border_color))
    print()


def print_scan_header(tickers: List[str], timeframes: List[str], n_candles: int):
    """Print a formatted scan start banner."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print()
    print(_c("═" * 60, _CYAN))
    print(_c("  🔍  iTrade Agentic Trend Scanner", _CYAN + _BOLD))
    print(_c(f"  {now}", _GREY))
    print(_c(f"  Tickers:    {', '.join(tickers)}", _BLUE))
    print(_c(f"  Timeframes: {', '.join(timeframes)}", _BLUE))
    print(_c(f"  Candles:    {n_candles} per timeframe", _BLUE))
    print(_c("═" * 60, _CYAN))
    print()


def print_scan_summary(results: List[TrendResult]):
    """Print an end-of-scan summary."""
    uptrends   = [r for r in results if r.direction == "up"]
    downtrends = [r for r in results if r.direction == "down"]
    no_trends  = [r for r in results if r.direction == "none"]

    print()
    print(_c("─" * 60, _GREY))
    print(_c("  📋  SCAN SUMMARY", _BOLD))
    print(_c(f"  Total scanned : {len(results)}", _GREY))
    print(_c(f"  🚀 Uptrends   : {len(uptrends)}", _GREEN))
    print(_c(f"  🔻 Downtrends : {len(downtrends)}", _RED))
    print(_c(f"  ➡️  No trend   : {len(no_trends)}", _GREY))

    vetoed = [r for r in results if r.veto_killed]
    print(_c(f"  ⚡ Veto-killed  : {len(vetoed)}", _YELLOW))

    if uptrends or downtrends:
        print(_c("\n  DETECTED TRENDS:", _BOLD))
        for r in sorted(uptrends + downtrends, key=lambda x: x.score, reverse=True):
            print(_c(f"    {r.emoji} {r.ticker:<12} {r.timeframe:<4}  {r.direction_label:<10}  [{r.score}/5  conf={r.confidence:.0%}]", _BOLD))

    if vetoed:
        print(_c("\n  VETO-KILLED (core signals passed but market was not clean):", _YELLOW))
        for r in vetoed:
            print(_c(f"    ⚡ {r.ticker:<12} {r.timeframe:<4}  [{', '.join(r.vetoes_failed)}]", _YELLOW))

    print(_c("─" * 64, _GREY))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CSV LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def log_result(result: TrendResult):
    """Append a TrendResult to the CSV log file."""
    cfg = CFG.alerts
    os.makedirs(cfg.log_dir, exist_ok=True)
    log_path = os.path.join(cfg.log_dir, cfg.log_file)

    row = result.to_dict()
    row["timestamp"] = datetime.now().isoformat()

    file_exists = os.path.isfile(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def log_all(results: List[TrendResult]):
    """Log all results to CSV."""
    for r in results:
        log_result(r)
