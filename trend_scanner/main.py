"""
main.py — iTrade Agentic Trend Scanner — CLI entry point.

Default mode: continuous dual-loop, fully parallelised per ticker.
  • 1h loop  – all tickers on 1h timeframe, every 24h (configurable)
  • 1m loop  – all tickers on 1m timeframe, every 3h (configurable)
Both loops start immediately and run concurrently until Ctrl+C.

Examples:
  python -m trend_scanner.main                        # dual-loop, default tickers
  python -m trend_scanner.main --tickers AAPL BTC-USD # specific tickers
  python -m trend_scanner.main --workers 30           # more parallelism
  python -m trend_scanner.main --telegram             # Telegram alerts on
  python -m trend_scanner.main --once --timeframes 1h # single scan, then exit
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional

from trend_scanner.config import CFG, DEFAULT_TICKERS
from trend_scanner.data.fetcher import fetch
from trend_scanner.engine.trend_engine import TrendEngine, TrendResult
from trend_scanner.charts.generator import generate_chart
from trend_scanner.vlm.qwen_agent import verify_chart, check_vlm_available
from trend_scanner.alerts.notifier import (
    print_result,
    print_scan_summary,
    log_all,
)
from trend_scanner.alerts.dispatcher import dispatch_trend_alert, DISPATCHER


# ─────────────────────────────────────────────────────────────────────────────
# THREAD SAFETY
# ─────────────────────────────────────────────────────────────────────────────

_print_lock = threading.Lock()
_csv_lock   = threading.Lock()


def _locked_print(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# PER-TICKER WORKER  (one thread per ticker)
# ─────────────────────────────────────────────────────────────────────────────

def _scan_one(
    ticker: str,
    timeframe: str,
    n_candles: int,
    vlm_enabled: bool,
    verbose: bool,
    save_all_charts: bool = False,
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

    # Save chart only for trending tickers by default.
    # --save-all-charts enables saving for every ticker (dev/debug mode).
    chart_path = None
    if result.is_trending or save_all_charts:
        chart_path = generate_chart(df, result, timeframe=timeframe)
    if chart_path:
        if timeframe in ("1h", "2h", "4h"):
            result.chart_1h_path = chart_path
        else:
            result.chart_1d_path = chart_path

    if (
        vlm_enabled
        and result.is_trending
        and result.score >= CFG.vlm.min_score_to_verify
        and chart_path
    ):
        verdict, conf, _ = verify_chart(chart_path)
        result.vlm_verdict    = verdict
        result.vlm_confidence = conf

    # Print entire result block atomically so concurrent workers don't interleave
    with _print_lock:
        print_result(result, verbose=verbose)

    dispatch_trend_alert(result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PARALLEL SCAN  (one call = all tickers for one timeframe)
# ─────────────────────────────────────────────────────────────────────────────

def run_parallel_scan(
    tickers: List[str],
    timeframe: str,
    n_candles: int,
    workers: int = 20,
    vlm_enabled: bool = False,
    print_all: bool = False,
    verbose: bool = True,
    save_all_charts: bool = False,
    scan_label: str = "SCAN",
) -> List[TrendResult]:
    """
    Submit all tickers to the thread pool and collect results.
    Returns a list of TrendResult (data-failure tickers are excluded).
    """
    CFG.alerts.print_all = print_all
    CFG.alerts.save_all_charts = save_all_charts

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _print_lock:
        print(f"\n{'═' * 60}")
        print(f"  {scan_label}  [{timeframe.upper()}]  {now}")
        print(f"  {len(tickers)} tickers  ·  {workers} workers  ·  {n_candles} candles")
        print(f"{'═' * 60}")

    results: List[TrendResult] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_scan_one, ticker, timeframe, n_candles, vlm_enabled, verbose, save_all_charts): ticker
            for ticker in tickers
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                result = fut.result()
                if result is not None:
                    results.append(result)
            except Exception as exc:
                _locked_print(f"  [ERR] {ticker} [{timeframe}]: {exc}")

    # with _print_lock:
    #     print_scan_summary(results)

    with _csv_lock:
        log_all(results)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# LOOP RUNNER  (one thread per timeframe)
# ─────────────────────────────────────────────────────────────────────────────

def _scan_loop(
    timeframe: str,
    interval_sec: int,
    tickers: List[str],
    n_candles: int,
    workers: int,
    vlm_enabled: bool,
    print_all: bool,
    verbose: bool,
    save_all_charts: bool,
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
            workers=workers,
            vlm_enabled=vlm_enabled,
            print_all=print_all,
            verbose=verbose,
            save_all_charts=save_all_charts,
            scan_label=f"SCAN #{scan_count}",
        )
        # Sleep in 1-second increments so Ctrl+C is responsive
        for _ in range(interval_sec):
            if stop_event.is_set():
                return
            time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# CONTINUOUS DUAL-LOOP  (1h + 1m running in parallel threads)
# ─────────────────────────────────────────────────────────────────────────────

def run_continuous(
    tickers: List[str],
    hourly_interval_sec: int,
    minutely_interval_sec: int,
    workers: int,
    vlm_enabled: bool = False,
    print_all: bool = False,
    verbose: bool = True,
    save_all_charts: bool = False,
):
    """
    Start two background threads — one for hourly 1h scans, one for 1m scans.
    Blocks until Ctrl+C, then shuts down cleanly.
    """
    stop_event = threading.Event()

    hourly_thread = threading.Thread(
        target=_scan_loop,
        kwargs=dict(
            timeframe="1h",
            interval_sec=hourly_interval_sec,
            tickers=tickers,
            n_candles=CFG.trend.analysis_window_1h,
            workers=workers,
            vlm_enabled=vlm_enabled,
            print_all=print_all,
            verbose=verbose,
            save_all_charts=save_all_charts,
            stop_event=stop_event,
        ),
        daemon=True,
        name="scan-1h",
    )
    minutely_thread = threading.Thread(
        target=_scan_loop,
        kwargs=dict(
            timeframe="1m",
            interval_sec=minutely_interval_sec,
            tickers=tickers,
            n_candles=CFG.trend.analysis_window_1m,
            workers=workers,
            vlm_enabled=vlm_enabled,
            print_all=print_all,
            verbose=verbose,
            save_all_charts=save_all_charts,
            stop_event=stop_event,
        ),
        daemon=True,
        name="scan-1m",
    )

    print(f"\n  Continuous dual-loop scanner started.")
    def _fmt(sec: int) -> str:
        return f"{sec // 3600}h" if sec >= 3600 else f"{sec // 60}m"

    print(f"  1h scan  — every {_fmt(hourly_interval_sec)},  {len(tickers)} tickers, {workers} workers")
    print(f"  1m scan  — every {_fmt(minutely_interval_sec)},  {len(tickers)} tickers, {workers} workers")
    print(f"  Ctrl+C to stop.\n")

    hourly_thread.start()
    minutely_thread.start()

    try:
        while hourly_thread.is_alive() or minutely_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n  Stopping — waiting for current scans to finish (max 30s)...")
        stop_event.set()
        hourly_thread.join(timeout=30)
        minutely_thread.join(timeout=30)
        print("  Goodbye!\n")
        sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE-SHOT SCAN  (--once mode, backwards-compatible)
# ─────────────────────────────────────────────────────────────────────────────

def run_once(
    tickers: List[str],
    timeframes: List[str],
    n_candles: int,
    workers: int,
    vlm_enabled: bool = False,
    print_all: bool = False,
    verbose: bool = True,
    save_all_charts: bool = False,
):
    for tf in timeframes:
        run_parallel_scan(
            tickers=tickers,
            timeframe=tf,
            n_candles=n_candles,
            workers=workers,
            vlm_enabled=vlm_enabled,
            print_all=print_all,
            verbose=verbose,
            save_all_charts=save_all_charts,
            scan_label="ONE-SHOT SCAN",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        prog="trend_scanner",
        description="iTrade Agentic Trend Scanner — parallel dual-loop (1h + 1m)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--tickers", "-t", nargs="+", metavar="TICKER",
                   help="Ticker symbols to scan. Defaults to config list.")
    p.add_argument("--workers", "-w", type=int, default=20, metavar="N",
                   help="Parallel worker threads per scan (default: 20)")
    p.add_argument("--hourly-interval", type=int, default=1440, metavar="MIN",
                   help="Minutes between 1h scans (default: 1440 = 24h)")
    p.add_argument("--minute-interval", type=int, default=180, metavar="MIN",
                   help="Minutes between 1m scans (default: 180 = 3h)")
    p.add_argument("--once", action="store_true",
                   help="Run a single scan pass then exit (use --timeframes to pick TFs)")
    p.add_argument("--timeframes", "-tf", nargs="+", metavar="TF", default=["1h", "1m"],
                   help="Timeframes for --once mode (default: 1h 1m)")
    p.add_argument("--candles", "-c", type=int, default=None, metavar="N",
                   help="Override candle count (applies to --once mode)")
    p.add_argument("--vlm", action="store_true",
                   help="Enable Qwen2.5-VL visual verification (requires local Ollama)")
    p.add_argument("--telegram", action="store_true",
                   help="Enable Telegram notifications for detected trends")
    p.add_argument("--min-signals", type=int, default=None, metavar="N",
                   help=f"Minimum signals to declare a trend (1-5, default: {CFG.trend.min_signals_for_trend})")
    p.add_argument("--all", "-a", action="store_true", dest="print_all",
                   help="Print one-liner for every ticker scanned, not just detected trends")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Suppress per-signal detail, show headline result only")
    p.add_argument("--save-all-charts", action="store_true", dest="save_all_charts",
                   help="Save charts for ALL tickers, not just those with a detected trend (dev/debug mode)")
    return p.parse_args()


def main():
    args = _parse_args()

    # ── Apply overrides ──────────────────────────────────────────────────────
    tickers = [t.upper() for t in args.tickers] if args.tickers else DEFAULT_TICKERS

    if args.min_signals:
        CFG.trend.min_signals_for_trend = args.min_signals
    if args.telegram:
        CFG.notifications.telegram.enabled = True

    # ── VLM pre-flight ───────────────────────────────────────────────────────
    vlm_enabled = args.vlm
    if vlm_enabled:
        print(f"\n  Checking VLM ({CFG.vlm.model})...")
        if not check_vlm_available():
            print(f"  VLM model {CFG.vlm.model} not found. Pull with: ollama pull {CFG.vlm.model}")
            print("  Continuing in math-only mode.\n")
            vlm_enabled = False
        else:
            print(f"  VLM ready: {CFG.vlm.model}\n")

    workers         = args.workers
    verbose         = not args.quiet
    print_all       = args.print_all
    save_all_charts = args.save_all_charts

    # ── One-shot mode ────────────────────────────────────────────────────────
    if args.once:
        n_candles = args.candles or CFG.data.n_candles
        run_once(
            tickers=tickers,
            timeframes=args.timeframes,
            n_candles=n_candles,
            workers=workers,
            vlm_enabled=vlm_enabled,
            print_all=print_all,
            verbose=verbose,
            save_all_charts=save_all_charts,
        )
        return

    # ── Continuous dual-loop (default) ───────────────────────────────────────
    hourly_interval_sec   = args.hourly_interval * 60
    minutely_interval_sec = args.minute_interval * 60  # arg is in minutes for consistency

    run_continuous(
        tickers=tickers,
        hourly_interval_sec=hourly_interval_sec,
        minutely_interval_sec=minutely_interval_sec,
        workers=workers,
        vlm_enabled=vlm_enabled,
        print_all=print_all,
        verbose=verbose,
        save_all_charts=save_all_charts,
    )


if __name__ == "__main__":
    main()
