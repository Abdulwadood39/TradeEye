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

    if not is_trend and not getattr(result, "veto_killed", False) and not CFG.alerts.print_all:
        # One-liner for clean no-trend (not veto-killed)
        print(
            _c(f"  ➡️  {result.ticker:<12} {result.timeframe:<4}", _GREY) +
            _c(f"  NO TREND  ", _GREY) +
            _c(f"score={result.score}/5", _GREY)
        )
        return

    # ── Full alert box ───────────────────────────────────────────────────────
    if getattr(result, "veto_killed", False):
        direction_label = "VETOED (FALSE POSITIVE)"
        border_color = _RED
        direction_color = _RED
    else:
        direction_label = result.direction_label
        border_color = _GREEN if result.direction == "up" else (_RED if result.direction == "down" else _GREY)
        direction_color = _GREEN if result.direction == "up" else _RED

    border = "─" * 60

    print()
    print(_c(border, border_color))

    print(_c(f"  {result.emoji}  {direction_label}", direction_color + _BOLD) +
          _c(f"  ·  {result.ticker}  ·  {result.timeframe}", _BOLD))

    score_bar = "█" * result.score + "░" * (5 - result.score)
    print(_c(f"  Score: [{score_bar}] {result.score}/5  ", _CYAN) +
          _c(f"Confidence: {result.confidence:.0%}", _YELLOW) +
          _c(f"  Candles: {result.candles_analyzed}", _GREY))

    if verbose and result.signals:
        print(_c("  Signals:", _BLUE))
        for sig in result.signals:
            if getattr(sig, "is_veto", False):
                icon = "✓" if sig.passed else "🛑"
                col = _GREY if sig.passed else _RED
                status = "PASS" if sig.passed else "VETO FAILED"
                detail_str = "  ".join(f"{k}={v}" for k, v in sig.detail.items())
                print(
                    _c(f"    {icon} {sig.name:<32}", col) +
                    _c(f"[{status}]  {detail_str}", col)
                )
            else:
                icon = "✓" if sig.passed else "✗"
                col = _GREEN if sig.passed else _GREY
                detail_str = "  ".join(f"{k}={v}" for k, v in sig.detail.items())
                print(
                    _c(f"    {icon} {sig.name:<32}", col) +
                    _c(f"score={sig.score:.0%}  {detail_str}", _GREY)
                )

    if result.vlm_verdict:
        vlm_col = _GREEN if "uptrend" in result.vlm_verdict else _RED
        print(_c(f"  🤖 VLM ({CFG.vlm.model}): {result.vlm_verdict}", vlm_col) +
              (f"  conf={result.vlm_confidence:.0%}" if result.vlm_confidence else ""))

    if result.chart_1h_path:
        print(_c(f"  📊 Chart: {result.chart_1h_path}", _CYAN))

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
    print(_c(f"  Data Fetch: {n_candles} candles maximum per timeframe", _BLUE))
    
    cfg = CFG.trend
    analysis_strs = []
    if "1m" in timeframes: analysis_strs.append(f"1m={cfg.analysis_window_1m}")
    if "1h" in timeframes: analysis_strs.append(f"1h={cfg.analysis_window_1h}")
    other_tfs = [t for t in timeframes if t not in ("1m", "1h")]
    if other_tfs: analysis_strs.append(f"others={cfg.analysis_window}")
    
    print(_c(f"  Analysis:   {', '.join(analysis_strs)} candles per scan", _YELLOW))
    print(_c("═" * 60, _CYAN))
    print()


def print_scan_summary(results: List[TrendResult]):
    """Print an end-of-scan summary."""
    uptrends   = [r for r in results if r.direction == "up"]
    downtrends = [r for r in results if r.direction == "down"]
    vetoed     = [r for r in results if getattr(r, "veto_killed", False)]
    no_trends  = [r for r in results if r.direction == "none" and not getattr(r, "veto_killed", False)]

    print()
    print(_c("─" * 60, _GREY))
    print(_c("  📋  SCAN SUMMARY", _BOLD))
    print(_c(f"  Total scanned : {len(results)}", _GREY))
    print(_c(f"  🚀 Uptrends   : {len(uptrends)}", _GREEN))
    print(_c(f"  🔻 Downtrends : {len(downtrends)}", _RED))
    print(_c(f"  🛑 Vetoed     : {len(vetoed)} (false positives killed)", _YELLOW))
    print(_c(f"  ➡️  No trend   : {len(no_trends)}", _GREY))

    if uptrends or downtrends:
        print(_c("\n  DETECTED TRENDS:", _BOLD))
        for r in uptrends + downtrends:
            print(_c(f"    {r.emoji} {r.ticker:<12} {r.timeframe:<4}  {r.direction_label:<10}  [{r.score}/5]", _BOLD))

    print(_c("─" * 60, _GREY))
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
