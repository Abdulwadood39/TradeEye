"""
notifier.py — Terminal alerts and CSV logging for trend detections.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
from datetime import datetime
from typing import List

from trend_scanner.config import CFG
from trend_scanner.engine.trend_engine import TrendResult

logger = logging.getLogger(__name__)


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

    Default (server-friendly): only prints detected trends (full box).
    With --all / print_all=True: also prints one-liner for no-trend tickers.
    """
    verbose = verbose if verbose is not None else CFG.alerts.verbose
    is_trend = result.is_trending

    if not is_trend:
        if not CFG.alerts.print_all:
            # Server mode: suppress no-trend noise — summary already shows counts
            return
        # --all: compact one-liner so the user knows it was scanned
        status = "VETOED" if getattr(result, "veto_killed", False) else "NO TREND"
        logger.info(
            _c(f"  ➡️  {result.ticker:<12} {result.timeframe:<4}", _GREY) +
            _c(f"  {status:<10}", _GREY) +
            _c(f"score={result.score}/5", _GREY)
        )
        return

    # ── Full alert box (trending tickers only) ───────────────────────────────
    if getattr(result, "veto_killed", False):
        direction_label = "VETOED (FALSE POSITIVE)"
        border_color = _RED
        direction_color = _RED
    else:
        direction_label = result.direction_label
        border_color = _GREEN if result.direction == "up" else (_RED if result.direction == "down" else _GREY)
        direction_color = _GREEN if result.direction == "up" else _RED

    border = "─" * 60

    logger.info("")
    logger.info(_c(border, border_color))

    logger.info(
        _c(f"  {result.emoji}  {direction_label}", direction_color + _BOLD) +
        _c(f"  ·  {result.ticker}  ·  {result.timeframe}", _BOLD)
    )

    score_bar = "█" * result.score + "░" * (5 - result.score)
    logger.info(
        _c(f"  Score: [{score_bar}] {result.score}/5  ", _CYAN) +
        _c(f"Confidence: {result.confidence:.0%}", _YELLOW) +
        _c(f"  Candles: {result.candles_analyzed}", _GREY)
    )

    if result.veto_killed:
        print(_c(f"  ⚡ VETOED by: {', '.join(result.vetoes_failed)}", _YELLOW + _BOLD))

    if verbose and result.signals:
        logger.info(_c("  Signals:", _BLUE))
        for sig in result.signals:
            if getattr(sig, "is_veto", False):
                icon = "✓" if sig.passed else "🛑"
                col = _GREY if sig.passed else _RED
                status = "PASS" if sig.passed else "VETO FAILED"
                detail_str = "  ".join(f"{k}={v}" for k, v in sig.detail.items())
                logger.info(
                    _c(f"    {icon} {sig.name:<32}", col) +
                    _c(f"[{status}]  {detail_str}", col)
                )
            else:
                icon = "✓" if sig.passed else "✗"
                col = _GREEN if sig.passed else _GREY
                detail_str = "  ".join(f"{k}={v}" for k, v in sig.detail.items())
                logger.info(
                    _c(f"    {icon} {sig.name:<32}", col) +
                    _c(f"score={sig.score:.0%}  {detail_str}", _GREY)
                )

    if result.vlm_verdict:
        vlm_col = _GREEN if "uptrend" in result.vlm_verdict else _RED
        logger.info(
            _c(f"  🤖 VLM ({CFG.vlm.model}): {result.vlm_verdict}", vlm_col) +
            (f"  conf={result.vlm_confidence:.0%}" if result.vlm_confidence else "")
        )

    if result.chart_1h_path:
        logger.info(_c(f"  📊 Chart: {result.chart_1h_path}", _CYAN))

    logger.info(_c(border, border_color))
    logger.info("")


def print_scan_header(tickers: List[str], timeframes: List[str], n_candles: int):
    """Print a formatted scan start banner."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("")
    logger.info(_c("═" * 60, _CYAN))
    logger.info(_c("  🔍  iTrade Agentic Trend Scanner", _CYAN + _BOLD))
    logger.info(_c(f"  {now}", _GREY))
    logger.info(_c(f"  Tickers:    {', '.join(tickers)}", _BLUE))
    logger.info(_c(f"  Timeframes: {', '.join(timeframes)}", _BLUE))
    logger.info(_c(f"  Data Fetch: {n_candles} candles maximum per timeframe", _BLUE))

    cfg = CFG.trend
    analysis_strs = []
    if "1m" in timeframes: analysis_strs.append(f"1m={cfg.analysis_window_1m}")
    if "1h" in timeframes: analysis_strs.append(f"1h={cfg.analysis_window_1h}")
    other_tfs = [t for t in timeframes if t not in ("1m", "1h")]
    if other_tfs: analysis_strs.append(f"others={cfg.analysis_window}")

    logger.info(_c(f"  Analysis:   {', '.join(analysis_strs)} candles per scan", _YELLOW))
    logger.info(_c("═" * 60, _CYAN))
    logger.info("")


def print_scan_summary(results: List[TrendResult]):
    """Print an end-of-scan summary."""
    uptrends   = [r for r in results if r.direction == "up"]
    downtrends = [r for r in results if r.direction == "down"]
    vetoed     = [r for r in results if getattr(r, "veto_killed", False)]
    no_trends  = [r for r in results if r.direction == "none" and not getattr(r, "veto_killed", False)]

    logger.info("")
    logger.info(_c("─" * 60, _GREY))
    logger.info(_c("  📋  SCAN SUMMARY", _BOLD))
    logger.info(_c(f"  Total scanned : {len(results)}", _GREY))
    logger.info(_c(f"  🚀 Uptrends   : {len(uptrends)}", _GREEN))
    logger.info(_c(f"  🔻 Downtrends : {len(downtrends)}", _RED))
    logger.info(_c(f"  🛑 Vetoed     : {len(vetoed)} (false positives killed)", _YELLOW))
    logger.info(_c(f"  ➡️  No trend   : {len(no_trends)}", _GREY))

    vetoed = [r for r in results if r.veto_killed]
    print(_c(f"  ⚡ Veto-killed  : {len(vetoed)}", _YELLOW))

    if uptrends or downtrends:
        logger.info(_c("\n  DjpgETECTED TRENDS:", _BOLD))
        for r in uptrends + downtrends:
            logger.info(_c(f"    {r.emoji} {r.ticker:<12} {r.timeframe:<4}  {r.direction_label:<10}  [{r.score}/5]", _BOLD))

    logger.info(_c("─" * 60, _GREY))
    logger.info("")


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
