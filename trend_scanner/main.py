"""
main.py — iTrade Agentic Trend Scanner — CLI entry point.

Usage examples:
  # Scan default tickers
  python -m trend_scanner.main

  # Scan specific tickers (auto-detects crypto vs stock)
  python -m trend_scanner.main --tickers AAPL BTC-USD ETH-USD GC=F NVDA

  # Custom candle count and timeframes
  python -m trend_scanner.main --tickers TSLA --candles 3000 --timeframes 1h 1d

  # Enable Qwen2.5-VL visual verification
  python -m trend_scanner.main --tickers BTC-USD --vlm

  # Continuous watch mode (re-scan every 60 minutes)
  python -m trend_scanner.main --tickers BTC-USD ETH-USD --watch --interval 60

  # Show all results (including no-trend)
  python -m trend_scanner.main --tickers AAPL --all
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from typing import List, Optional

from trend_scanner.config import CFG, DEFAULT_TICKERS
from trend_scanner.data.fetcher import fetch
from trend_scanner.engine.trend_engine import TrendEngine, TrendResult
from trend_scanner.charts.generator import generate_chart
from trend_scanner.vlm.qwen_agent import verify_chart, check_vlm_available
from trend_scanner.alerts.notifier import (
    print_result,
    print_scan_header,
    print_scan_summary,
    log_all,
)
from trend_scanner.alerts.dispatcher import dispatch_trend_alert


# ─────────────────────────────────────────────────────────────────────────────
# SCAN LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def run_scan(
    tickers: List[str],
    timeframes: List[str],
    n_candles: int,
    vlm_enabled: bool = False,
    print_all: bool = False,
    verbose: bool = True,
) -> List[TrendResult]:
    """
    Run one full scan pass across all tickers and timeframes.

    Returns
    -------
    List[TrendResult] — one per (ticker, timeframe) pair
    """
    print_scan_header(tickers, timeframes, n_candles)

    engine = TrendEngine()
    all_results: List[TrendResult] = []

    for ticker in tickers:
        for tf in timeframes:
            print(f"  Fetching {ticker} [{tf}] ...")

            # 1. Fetch data
            df = fetch(ticker, tf, n_candles)
            if df is None or len(df) < 50:
                print(f"  [SKIP] {ticker} {tf}: insufficient data\n")
                continue

            # 2. Trend analysis
            result = engine.analyze(df, ticker=ticker, timeframe=tf)

            # 3. Generate chart (always — useful for visual review)
            chart_path = generate_chart(df, result, timeframe=tf)
            if chart_path:
                if tf in ("1h", "2h", "4h"):
                    result.chart_1h_path = chart_path
                else:
                    result.chart_1d_path = chart_path

            # 4. Optional VLM verification (only if trend detected + score threshold met)
            if (
                vlm_enabled
                and result.is_trending
                and result.score >= CFG.vlm.min_score_to_verify
                and chart_path
            ):
                print(f"  🤖 Running VLM verification on {ticker} {tf} chart...")
                verdict, conf, reasoning = verify_chart(chart_path)
                result.vlm_verdict    = verdict
                result.vlm_confidence = conf
                if reasoning:
                    print(f"     VLM: {reasoning}")

            # 5. Print result
            CFG.alerts.print_all = print_all
            print_result(result, verbose=verbose)

            # 6. Dispatch external alerts
            dispatch_trend_alert(result)

            all_results.append(result)

    # Summary + CSV log
    print_scan_summary(all_results)
    log_all(all_results)
    _print_log_path()

    return all_results


def _print_log_path():
    import os
    log_path = os.path.join(CFG.alerts.log_dir, CFG.alerts.log_file)
    print(f"  💾 Log saved: {os.path.abspath(log_path)}")
    print(f"  📂 Charts:    {os.path.abspath(CFG.chart.output_dir)}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        prog="trend_scanner",
        description="iTrade Agentic Trend Scanner — detects sustained up/down trends using 5 mathematical signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--tickers", "-t",
        nargs="+",
        default=None,
        metavar="TICKER",
        help="Ticker symbols to scan (e.g. AAPL BTC-USD GC=F). Defaults to config list.",
    )

    parser.add_argument(
        "--timeframes", "-tf",
        nargs="+",
        default=None,
        metavar="TF",
        help="Timeframes to scan (e.g. 1h 1d). Default: 1h 1d",
    )

    parser.add_argument(
        "--candles", "-c",
        type=int,
        default=None,
        metavar="N",
        help=f"Number of candles to analyse. Default: {CFG.data.n_candles}",
    )

    parser.add_argument(
        "--vlm",
        action="store_true",
        help="Enable Qwen2.5-VL visual verification via local Ollama (slower but adds visual crosscheck)",
    )

    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Enable Telegram notifications for detected trends",
    )

    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Continuous watch mode: re-scan on an interval",
    )

    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=60,
        metavar="MINUTES",
        help="Re-scan interval in minutes (only in --watch mode). Default: 60",
    )

    parser.add_argument(
        "--min-signals", "-ms",
        type=int,
        default=None,
        metavar="N",
        help=f"Minimum signals required to declare a trend (1–5). Default: {CFG.trend.min_signals_for_trend}",
    )

    parser.add_argument(
        "--candle-window",
        type=int,
        default=None,
        metavar="N",
        help="Analysis window size in candles. Default matches --candles",
    )

    parser.add_argument(
        "--all", "-a",
        action="store_true",
        dest="print_all",
        help="Print all results including no-trend tickers",
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress verbose signal breakdown (only show headline result)",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # ── Apply arg overrides to CFG ───────────────────────────────────────────
    tickers    = [t.upper() for t in args.tickers] if args.tickers else DEFAULT_TICKERS
    timeframes = args.timeframes or CFG.data.timeframes
    n_candles  = args.candles or CFG.data.n_candles

    if args.min_signals:
        CFG.trend.min_signals_for_trend = args.min_signals

    if args.candle_window:
        CFG.trend.analysis_window = args.candle_window
    else:
        CFG.trend.analysis_window = n_candles

    CFG.vlm.enabled = args.vlm
    if args.telegram:
        CFG.notifications.telegram.enabled = True

    # ── VLM pre-flight ───────────────────────────────────────────────────────
    if args.vlm:
        print(f"\n  Checking VLM availability ({CFG.vlm.model})...")
        if not check_vlm_available():
            print(f"  ⚠️  Model {CFG.vlm.model} not found in Ollama.")
            print(f"     Pull it with: ollama pull {CFG.vlm.model}")
            print("     Continuing with math-only mode.\n")
            CFG.vlm.enabled = False
        else:
            print(f"  ✅ VLM ready: {CFG.vlm.model}\n")

    # ── Run ──────────────────────────────────────────────────────────────────
    if args.watch:
        print(f"  👁  Watch mode: scanning every {args.interval} minute(s). Ctrl+C to stop.\n")
        scan_count = 0
        try:
            while True:
                scan_count += 1
                print(f"\n{'='*60}")
                print(f"  SCAN #{scan_count}  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*60}")
                run_scan(
                    tickers=tickers,
                    timeframes=timeframes,
                    n_candles=n_candles,
                    vlm_enabled=CFG.vlm.enabled,
                    print_all=args.print_all,
                    verbose=not args.quiet,
                )
                print(f"\n  💤 Next scan in {args.interval} minute(s)...")
                time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            print("\n\n  Scan stopped. Goodbye! 👋\n")
            sys.exit(0)
    else:
        run_scan(
            tickers=tickers,
            timeframes=timeframes,
            n_candles=n_candles,
            vlm_enabled=CFG.vlm.enabled,
            print_all=args.print_all,
            verbose=not args.quiet,
        )


if __name__ == "__main__":
    main()
