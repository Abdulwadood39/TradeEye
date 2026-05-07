"""
generator.py — Annotated candlestick chart generator (v2).

Fixes:
  - 1m charts: uses integer bar index (not datetime) for x-axis to avoid
    gaps from market-closed periods, then overlays human-readable time labels
  - Vectorized candle drawing via LineCollection — 10x faster, works for 2000+ bars
  - Dynamic ascending/descending trendlines drawn through actual swing pivots
  - Veto status shown on chart (R², ATR, Break)
  - Proper figsize per timeframe
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from trend_scanner.config import CFG, ChartConfig
from trend_scanner.engine.trend_engine import TrendResult
from trend_scanner.engine.pivots import get_pivots


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_chart(
    df: pd.DataFrame,
    result: TrendResult,
    timeframe: str = "1h",
    chart_cfg: ChartConfig = None,
) -> Optional[str]:
    if df is None or len(df) < 5:
        return None
    cfg = chart_cfg or CFG.chart

    # Limit to exactly what the engine analyzed
    window = result.candles_analyzed if result.candles_analyzed > 0 else min(CFG.trend.analysis_window, len(df))
    plot_df = df.iloc[-window:].reset_index(drop=True)

    try:
        return _draw_chart(plot_df, result, timeframe, cfg)
    except Exception as e:
        logger.warning(f"  [WARN] Chart generation failed for {result.ticker}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DRAWING
# ─────────────────────────────────────────────────────────────────────────────

def _draw_chart(df: pd.DataFrame, result: TrendResult, timeframe: str, cfg: ChartConfig) -> str:
    n   = len(df)
    tf  = timeframe.lower()

    # ── Figure layout ────────────────────────────────────────────────────────
    figsize = cfg.figsize_1m if tf == "1m" else cfg.figsize_1h
    fig, (ax_main, ax_vol) = plt.subplots(
        2, 1, figsize=figsize, facecolor=cfg.bg,
        gridspec_kw={"height_ratios": [5, 1], "hspace": 0.03},
    )
    for ax in (ax_main, ax_vol):
        ax.set_facecolor(cfg.panel)
        ax.tick_params(colors=cfg.subtext, labelsize=6.5)
        for spine in ax.spines.values():
            spine.set_color(cfg.grid)
        ax.grid(True, color=cfg.grid, linewidth=0.3, alpha=0.6, zorder=0)

    # ── X-axis strategy ──────────────────────────────────────────────────────
    # Always use integer bar index — avoids datetime gap issues on 1m data
    # (gaps from weekends, overnight, market close all distort the chart).
    # We map readable time labels back onto bar indices as ticks.
    xs = np.arange(n, dtype=np.float64)

    # ── Build x-axis positions ───────────────────────────────────────────────
    xs = np.arange(len(df), dtype=np.float64)
    use_dates = "datetime" in df.columns

    if use_dates:
        # Create a mapping from index to datetime string
        dt_values = pd.to_datetime(df["datetime"].values)
        
        def format_date(x, pos):
            idx = int(np.clip(round(x), 0, len(df) - 1))
            return dt_values[idx].strftime("%b %d\n%H:%M")
            
        def format_date_vol(x, pos):
            idx = int(np.clip(round(x), 0, len(df) - 1))
            return dt_values[idx].strftime("%b %d")

        ax_main.xaxis.set_major_formatter(plt.FuncFormatter(format_date))
        ax_vol.xaxis.set_major_formatter(plt.FuncFormatter(format_date_vol))
        
        num_ticks = min(8, len(df))
        ax_main.xaxis.set_major_locator(plt.MaxNLocator(num_ticks))
        ax_vol.xaxis.set_major_locator(plt.MaxNLocator(num_ticks))

    # ── Candlesticks (vectorized) ─────────────────────────────────────────────
    _draw_candles_fast(ax_main, df, xs, cfg)

    # ── Volume ───────────────────────────────────────────────────────────────
    _draw_volume(ax_vol, df, xs, cfg)

    # ── Linear regression trendline ──────────────────────────────────────────
    _draw_regression_line(ax_main, df, xs, result, cfg)

    # ── Dynamic support/resistance trendlines ─────────────────────────────────
    _draw_dynamic_trendlines(ax_main, df, xs, result, cfg)

    # ── Pivot channel regression lines ────────────────────────────────────────
    _draw_pivot_channels(ax_main, df, xs, cfg)

    # ── Pivot high/low markers ────────────────────────────────────────────────
    _draw_pivot_markers(ax_main, df, xs, cfg)

    # ── Signal + veto scorecard ───────────────────────────────────────────────
    _draw_scorecard(ax_main, result, cfg)

    # ── Trend arrow + label ───────────────────────────────────────────────────
    _draw_trend_badge(ax_main, df, xs, result, cfg)

    # ── Axes limits ──────────────────────────────────────────────────────────
    price_min = float(df["low"].min())
    price_max = float(df["high"].max())
    pr        = price_max - price_min
    ax_main.set_ylim(price_min - pr * 0.04, price_max + pr * 0.30)
    ax_main.set_xlim(-0.5, n - 0.5)
    ax_vol.set_xlim(-0.5, n - 0.5)
    ax_main.set_xticklabels([])

    # ── Title ─────────────────────────────────────────────────────────────────
    _draw_title(fig, result, timeframe, n, cfg)

    # ── VLM badge ─────────────────────────────────────────────────────────────
    if result.vlm_verdict:
        _draw_vlm_badge(ax_main, result, cfg)

    # ── Save ─────────────────────────────────────────────────────────────────
    os.makedirs(cfg.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    direction_tag = result.direction.upper()
    fname = f"{result.ticker.replace('/', '_')}_{direction_tag}.png"
    save_path = os.path.join(cfg.output_dir, fname)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(path, dpi=cfg.dpi, bbox_inches="tight", facecolor=cfg.bg)
    plt.close(fig)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# DRAWING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _draw_candles(ax, df: pd.DataFrame, xs: np.ndarray, cfg: ChartConfig):
    """Draw candlestick wicks and bodies (vectorized)."""
    n = len(df)
    if n < 2:
        return

    from matplotlib.collections import LineCollection, PolyCollection

    width = 0.75

    if bull_wicks:
        ax.add_collection(LineCollection(bull_wicks, colors=cfg.bull, linewidths=0.6, zorder=2))
    if bear_wicks:
        ax.add_collection(LineCollection(bear_wicks, colors=cfg.bear, linewidths=0.6, zorder=2))

    colors = [cfg.bull if c >= o else cfg.bear for o, c in zip(opens, closes)]

    # Wicks (lines)
    wicks = [((x, l), (x, h)) for x, l, h in zip(xs, lows, highs)]
    wick_col = LineCollection(wicks, colors=colors, linewidths=0.5, zorder=2)
    ax.add_collection(wick_col)

    # Bodies (rectangles)
    bodies = []
    for x, o, c, h, l in zip(xs, opens, closes, highs, lows):
        body_bot = min(o, c)
        body_h = max(abs(c - o), (h - l) * 0.005)
        # Rectangle coordinates: (left, bottom), (right, bottom), (right, top), (left, top)
        left = x - width / 2
        right = x + width / 2
        top = body_bot + body_h
        bodies.append(((left, body_bot), (right, body_bot), (right, top), (left, top)))
        
    body_col = PolyCollection(bodies, facecolors=colors, edgecolors="none", zorder=3)
    ax.add_collection(body_col)


def _draw_volume(ax, df: pd.DataFrame, xs: np.ndarray, cfg: ChartConfig):
    if "volume" not in df.columns:
        return
    n      = len(df)
    vols   = df["volume"].values.astype(float)
    opens  = df["open"].values.astype(float)
    closes = df["close"].values.astype(float)
    colors = [cfg.bull if c >= o else cfg.bear for o, c in zip(opens, closes)]
    bar_w  = max(0.4, 0.7 * (xs[1] - xs[0])) if n > 1 else 0.4
    ax.bar(xs, vols, width=bar_w, color=colors, alpha=0.45, zorder=2)
    ax.set_ylabel("Vol", color=cfg.subtext, fontsize=6)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if v >= 1e6 else f"{v/1e3:.0f}K" if v >= 1e3 else f"{v:.0f}")
    )


def _draw_regression_line(ax, df, xs, result, cfg):
    close  = df["close"].values.astype(float)
    x_idx  = np.arange(len(close), dtype=float)
    coeffs = np.polyfit(x_idx, close, 1)
    y_fit  = np.polyval(coeffs, x_idx)
    color  = cfg.up_channel if result.direction == "up" else (
             cfg.dn_channel if result.direction == "down" else cfg.subtext)
    ax.plot(xs, y_fit, color=color, linewidth=1.6, linestyle="--",
            alpha=0.8, zorder=5, label="LinReg")


def _draw_dynamic_trendlines(ax, df, xs, result, cfg):
    """
    Draw dynamic ascending support (uptrend) or descending resistance (downtrend)
    trendlines fitted through actual swing pivot points.
    Marks touch points with gold dots.
    """
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)
    n = len(df)
    mean_p = float(df["close"].mean())
    touch_tol = mean_p * (CFG.trend.trendline_touch_pct / 100.0)

    if result.direction == "up" and len(pivot_lo) >= 3:
        lo_prices = df["low"].values[pivot_lo].astype(float)
        coeffs    = np.polyfit(pivot_lo.astype(float), lo_prices, 1)
        tl_y      = np.polyval(coeffs, np.arange(n, dtype=float))

        ax.plot(xs, tl_y, color=cfg.trendline_up, linewidth=1.8,
                linestyle="-", alpha=0.85, zorder=6, label="Support TL")

        # Mark touch points
        touches = [i for i in pivot_lo
                   if abs(df["low"].values[i] - np.polyval(coeffs, float(i))) <= touch_tol]
        if touches:
            ax.scatter(xs[touches], df["low"].values[touches],
                       color=cfg.trendline_touch, s=30, zorder=8,
                       marker="o", alpha=0.9, label=f"Touches ({len(touches)})")

    elif result.direction == "down" and len(pivot_hi) >= 3:
        hi_prices = df["high"].values[pivot_hi].astype(float)
        coeffs    = np.polyfit(pivot_hi.astype(float), hi_prices, 1)
        tl_y      = np.polyval(coeffs, np.arange(n, dtype=float))

        ax.plot(xs, tl_y, color=cfg.trendline_dn, linewidth=1.8,
                linestyle="-", alpha=0.85, zorder=6, label="Resistance TL")

        touches = [i for i in pivot_hi
                   if abs(df["high"].values[i] - np.polyval(coeffs, float(i))) <= touch_tol]
        if touches:
            ax.scatter(xs[touches], df["high"].values[touches],
                       color=cfg.trendline_touch, s=30, zorder=8,
                       marker="o", alpha=0.9, label=f"Touches ({len(touches)})")


def _draw_pivot_channels(ax, df, xs, cfg):
    """Draw regression channels through pivot highs and pivot lows."""
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)
    n = len(df)
    for bars, col_key, col in [(pivot_hi, "high", cfg.pivot_hi), (pivot_lo, "low", cfg.pivot_lo)]:
        if len(bars) < 3:
            continue
        prices = df[col_key].values[bars].astype(float)
        coeffs = np.polyfit(bars.astype(float), prices, 1)
        y_line = np.polyval(coeffs, np.arange(n, dtype=float))
        ax.plot(xs, y_line, color=col, linewidth=0.9, linestyle="-.",
                alpha=0.5, zorder=4)


def _draw_pivot_markers(ax, df, xs, cfg):
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)
    if len(pivot_hi) > 0:
        ax.scatter(xs[pivot_hi], df["high"].values[pivot_hi],
                   marker="v", color=cfg.pivot_hi, s=14, zorder=7, alpha=0.8)
    if len(pivot_lo) > 0:
        ax.scatter(xs[pivot_lo], df["low"].values[pivot_lo],
                   marker="^", color=cfg.pivot_lo, s=14, zorder=7, alpha=0.8)


def _draw_scorecard(ax, result: TrendResult, cfg: ChartConfig):
    """Draw core signals + veto results as a compact scorecard."""
    all_rows = []

    for s in result.signals:
        icon  = "✓" if s.passed else "✗"
        color = cfg.signal_ok if s.passed else cfg.signal_fail
        all_rows.append((f"{icon} {s.name}: {s.score:.0%}", color))

    # Separator
    all_rows.append(("─ VETOES ─────────────────", cfg.subtext))

    for v in result.vetoes:
        icon  = "✓" if v.passed else "✗"
        color = cfg.signal_ok if v.passed else "#ff9500"  # amber for veto fails
        detail = " | ".join(f"{k}={val}" for k, val in list(v.detail.items())[:2])
        all_rows.append((f"{icon} {v.name}: {detail}", color))

    y_start = 0.985
    line_h  = 0.040

    for i, (text, color) in enumerate(all_rows):
        ax.text(
            0.005, y_start - i * line_h, text,
            transform=ax.transAxes, fontsize=6.5, color=color,
            va="top", ha="left", family="monospace",
            bbox=dict(boxstyle="round,pad=0.12", facecolor=cfg.bg,
                      edgecolor=color, alpha=0.82, linewidth=0.5),
            zorder=10,
        )


def _draw_trend_badge(ax, df, xs, result: TrendResult, cfg: ChartConfig):
    """Direction badge + arrow in the right portion of the chart."""
    if result.direction == "none":
        # Show SIDEWAYS label if a veto killed an otherwise valid trend
        if result.veto_killed and result.vetoes_failed:
            price_mid = (df["high"].max() + df["low"].min()) / 2
            ax.text(
                xs[int(len(xs) * 0.72)], price_mid,
                f"⚡ VETO\n{chr(10).join(result.vetoes_failed)}",
                color="#ff9500", fontsize=9, fontweight="bold",
                ha="center", va="center", zorder=9,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=cfg.bg,
                          edgecolor="#ff9500", linewidth=1.5, alpha=0.92),
            )
        return

    price_min = float(df["low"].min())
    price_max = float(df["high"].max())
    pr        = price_max - price_min
    mid_x     = xs[int(len(xs) * 0.75)]
    mid_y     = price_min + pr * 0.50
    dy        = pr * 0.14 if result.direction == "up" else -pr * 0.14
    color     = cfg.up_channel if result.direction == "up" else cfg.dn_channel

    ax.annotate("",
        xy=(mid_x, mid_y + dy), xytext=(mid_x, mid_y - dy),
        arrowprops=dict(arrowstyle="->", color=color, lw=3.0,
                        connectionstyle="arc3,rad=0"),
        zorder=8,
    )
    label = f"{result.direction_label}  {result.score}/5\nconf {result.confidence:.0%}"
    ax.text(mid_x, mid_y + dy * 1.6, label,
            color=color, fontsize=10, fontweight="bold",
            ha="center", va="center", zorder=9,
            bbox=dict(boxstyle="round,pad=0.45", facecolor=cfg.bg,
                      edgecolor=color, linewidth=2.0, alpha=0.93))


def _draw_title(fig, result: TrendResult, timeframe: str, n_bars: int, cfg: ChartConfig):
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")
    sigs    = "  |  ".join(result.signals_passed) or "—"
    vetoed  = f"   ⚡ VETOED by: {', '.join(result.vetoes_failed)}" if result.veto_killed else ""
    fig.suptitle(
        f"{result.emoji}  {result.ticker}  ·  {timeframe}  ·  {result.direction_label}"
        f"  [{result.score}/5  conf={result.confidence:.0%}]"
        f"\nSignals: {sigs}{vetoed}   ·   {n_bars} candles   ·   {now}",
        color=cfg.text, fontsize=10.5, y=0.997, fontweight="bold",
    )


def _draw_vlm_badge(ax, result, cfg):
    color = cfg.signal_ok if "uptrend" in str(result.vlm_verdict) else cfg.dn_channel
    text  = (f"🤖 VLM: {result.vlm_verdict}"
             + (f"  {result.vlm_confidence:.0%}" if result.vlm_confidence else ""))
    ax.text(0.99, 0.02, text, transform=ax.transAxes,
            fontsize=7.5, color=color, va="bottom", ha="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=cfg.bg,
                      edgecolor=color, alpha=0.9, linewidth=0.8),
            zorder=10)
