"""
main.py — iTrade Agentic Trend Scanner — entry point.

Configuration is managed through Python files in trend_scanner/config/:
  config/run.py            → mode, workers, intervals, verbosity
  config/signals.py        → signal thresholds
  config/vetoes.py         → veto gate thresholds
  config/notifications.py  → Discord / Telegram channels
  config/tickers.py        → default watchlists
  config/misc.py           → charting, VLM, data fetching

The only CLI argument is --tickers for ad-hoc overrides:
  python -m trend_scanner.main                          # use DEFAULT_TICKERS
  python -m trend_scanner.main --tickers AAPL MSFT NVDA # quick custom scan
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional

from trend_scanner.config import CFG, DEFAULT_TICKERS
from trend_scanner.data.fetcher import fetch
from trend_scanner.engine.trend_engine import TrendEngine, TrendResult
from trend_scanner.charts.generator import generate_chart
from trend_scanner.vlm.gemini_agent import verify_chart, check_vlm_available
from trend_scanner.alerts.notifier import print_result, log_all
from trend_scanner.alerts.dispatcher import dispatch_trend_alert, dispatch_text_message, DISPATCHER

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger("trend_scanner")
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)

    for lib in ("yfinance", "urllib3", "requests", "peewee", "asyncio", "ccxt"):
        logging.getLogger(lib).setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# THREAD SAFETY
# ─────────────────────────────────────────────────────────────────────────────

_print_lock = threading.Lock()
_csv_lock   = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# PER-TICKER WORKER
# ─────────────────────────────────────────────────────────────────────────────

def _scan_one(
    ticker: str,
    timeframe: str,
    n_candles: int,
    vlm_enabled: bool,
    ) -> Optional[TrendResult]:
    """
    Fetch + analyse one ticker/timeframe combination.
    Each call creates its own TrendEngine so threads don't share state.
    Returns TrendResult, or None when data is unavailable.
    """
    engine = TrendEngine()

    df = fetch(ticker, timeframe, n_candles)
    if df is None or len(df) < 50:
        return None

    result = engine.analyze(df, ticker=ticker, timeframe=timeframe)

    # Save chart for trending tickers (or all if save_all_charts is on)
    chart_path = None
    if result.is_trending or CFG.run.save_all_charts:
        chart_path = generate_chart(df, result, timeframe=timeframe)
    if chart_path:
        result.chart_path   = chart_path
        result.chart_1h_path = chart_path   # backward compat
        result.chart_1d_path = chart_path   # backward compat

    if (
        vlm_enabled
        and result.is_trending
        and result.score >= CFG.vlm.min_score_to_verify
        and chart_path
    ):
        verdict, conf, _ = verify_chart(chart_path)
        result.vlm_verdict    = verdict
        result.vlm_confidence = conf

    with _print_lock:
        print_result(result, verbose=CFG.run.verbose)

    dispatch_trend_alert(result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PARALLEL SCAN  (all tickers for one timeframe)
# ─────────────────────────────────────────────────────────────────────────────

def run_parallel_scan(
    tickers: List[str],
    timeframe: str,
    n_candles: int,
    vlm_enabled: bool = False,
    scan_label: str = "SCAN",
    ) -> List[TrendResult]:
    """
    Submit all tickers to the thread pool and collect results.
    Returns a list of TrendResult (data-failure tickers are excluded).
    """
    workers = CFG.run.workers

    # Sync alert config from run config
    CFG.alerts.print_all       = CFG.run.print_all
    CFG.alerts.save_all_charts = CFG.run.save_all_charts
    CFG.alerts.verbose         = CFG.run.verbose

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _print_lock:
        logger.info(f"\n{'═' * 60}")
        logger.info(f"  {scan_label}  [{timeframe.upper()}]  {now}")
        logger.info(f"  {len(tickers)} tickers  ·  {workers} workers  ·  {n_candles} candles")
        veto_state = "ON" if CFG.vetoes.enabled else "OFF ⚠️"
        logger.info(f"  vetoes={veto_state}  min_signals={CFG.trend.min_signals_for_trend}")
        logger.info(f"{'═' * 60}")

    # Clean up previous Discord messages before starting the new scan
    DISPATCHER.clear_discord_messages(timeframe=timeframe)

    if len(tickers) <= 10:
        tickers_str = ", ".join(tickers)
    else:
        tickers_str = f"{', '.join(tickers[:10])} and {len(tickers) - 10} more"

    start_message = (
        f"🔄 *{scan_label} Started* ({timeframe})\n"
        f"Scanning {len(tickers)} tickers ({tickers_str}) "
        f"analyzing the last {n_candles} candles."
    )
    dispatch_text_message(start_message, timeframe=timeframe)

    results: List[TrendResult] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_scan_one, ticker, timeframe, n_candles, vlm_enabled): ticker
            for ticker in tickers
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                result = fut.result()
                if result is not None:
                    results.append(result)
            except Exception as exc:
                logger.error(f"  [ERR] {ticker} [{timeframe}]: {exc}")

    with _csv_lock:
        log_all(results)

    # Flush buffered no-trend results as one consolidated Discord message
    DISPATCHER.flush_no_trend_batch(timeframe)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# LOOP RUNNER  (one thread per timeframe)
# ─────────────────────────────────────────────────────────────────────────────

def _scan_loop(
    timeframe: str,
    interval_sec: int,
    tickers: List[str],
    n_candles: int,
    vlm_enabled: bool,
    stop_event: threading.Event,
    ):
    """
    Repeatedly run parallel scans for `timeframe` every `interval_sec` seconds.
    Returns when `stop_event` is set.
    """
    scan_count = 0
    while not stop_event.is_set():
        scan_count += 1
        run_parallel_scan(
            tickers=tickers,
            timeframe=timeframe,
            n_candles=n_candles,
            vlm_enabled=vlm_enabled,
            scan_label=f"SCAN #{scan_count}",
        )
        # Sleep in 1-second increments so Ctrl+C is responsive
        for _ in range(interval_sec):
            if stop_event.is_set():
                return
            time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# CONTINUOUS MULTI-LOOP  (one thread per entry in CFG.run.intervals)
# ─────────────────────────────────────────────────────────────────────────────

def run_continuous(tickers: List[str], vlm_enabled: bool = False):
    """
    Start one background thread per timeframe in CFG.run.intervals.
    Adding '5m' or '30m' to [run.intervals] in scanner.toml is all it takes
    to spin up an additional scan loop — no code changes needed.

    Blocks until Ctrl+C, then shuts down cleanly.
    """
    intervals: Dict[str, int] = CFG.run.intervals   # {tf: minutes}
    if not intervals:
        logger.error("  [ERR] No timeframes configured in [run.intervals]. Check scanner.toml.")
        sys.exit(1)

    stop_event = threading.Event()
    threads = []

    def _fmt(minutes: int) -> str:
        if minutes >= 1440:
            return f"{minutes // 1440}d"
        if minutes >= 60:
            return f"{minutes // 60}h"
        return f"{minutes}m"

    logger.info(f"\n  Continuous scanner started — {len(intervals)} loop(s):")
    for tf, interval_min in sorted(intervals.items()):
        n_candles = CFG.trend.window_for(tf)
        t = threading.Thread(
            target=_scan_loop,
            kwargs=dict(
                timeframe=tf,
                interval_sec=interval_min * 60,
                tickers=tickers,
                n_candles=n_candles,
                vlm_enabled=vlm_enabled,
                stop_event=stop_event,
            ),
            daemon=True,
            name=f"scan-{tf}",
        )
        threads.append(t)
        logger.info(f"    [{tf}]  every {_fmt(interval_min)},  {len(tickers)} tickers,  {n_candles} candles")

    veto_state = "ON" if CFG.vetoes.enabled else "OFF ⚠️"
    logger.info(f"\n  vetoes={veto_state}  min_signals={CFG.trend.min_signals_for_trend}")
    logger.info("  Ctrl+C to stop.\n")

    for t in threads:
        t.start()

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("\n\n  Stopping — waiting for current scans to finish (max 30s)...")
        stop_event.set()
        for t in threads:
            t.join(timeout=30)
        logger.info("  Goodbye!\n")
        sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE-SHOT SCAN  (mode = "once")
# ─────────────────────────────────────────────────────────────────────────────

def run_once(tickers: List[str], vlm_enabled: bool = False):
    """
    Scan each timeframe in CFG.run.once.timeframes then exit.
    Timeframes are configured via [run.once] timeframes in scanner.toml / profiles.
    """
    timeframes = CFG.run.once.timeframes
    if not timeframes:
        logger.error("  [ERR] No timeframes configured in [run.once] timeframes. Check scanner.toml.")
        sys.exit(1)

    logger.info(f"\n  One-shot scan: {timeframes}")
    for tf in timeframes:
        n_candles = CFG.trend.window_for(tf)
        run_parallel_scan(
            tickers=tickers,
            timeframe=tf,
            n_candles=n_candles,
            vlm_enabled=vlm_enabled,
            scan_label="ONE-SHOT SCAN",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI  (only --profile remains)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        prog="trend_scanner",
        description="iTrade Agentic Trend Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--tickers", "-t",
        nargs="+",
        metavar="TICKER",
        default=None,
        help=(
            "Optional space-separated list of tickers to scan instead of DEFAULT_TICKERS. "
            "Example: --tickers AAPL MSFT NVDA BTC-USD"
        ),
    )
    return p.parse_args()


def main():
    _setup_logging()
    args = _parse_args()

    # Tickers: CLI override takes priority, otherwise use DEFAULT_TICKERS
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
        logger.info(f"\n  📌 Custom tickers ({len(tickers)}): {', '.join(tickers)}")
    else:
        tickers = DEFAULT_TICKERS

    # VLM pre-flight check
    vlm_enabled = CFG.vlm.enabled
    if vlm_enabled:
        logger.info(f"\n  Checking VLM ({CFG.vlm.model})...")
        if not check_vlm_available():
            logger.warning(f"  VLM model {CFG.vlm.model} not found.")
            logger.info("  Continuing in math-only mode.\n")
            vlm_enabled = False
        else:
            logger.info(f"  VLM ready: {CFG.vlm.model}\n")

    # Dispatch based on configured mode (edit config/run.py to change)
    if CFG.run.mode == "once":
        run_once(tickers=tickers, vlm_enabled=vlm_enabled)
    else:
        run_continuous(tickers=tickers, vlm_enabled=vlm_enabled)


if __name__ == "__main__":
    main()
