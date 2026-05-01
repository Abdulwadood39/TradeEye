"""
generator.py — Annotated candlestick chart generator for the trend scanner.

Produces:
  1. Zoomed-out overview chart (full 2000-candle window) with:
     - Dark GitHub theme
     - Candlesticks
     - Regression trendline on close
     - Pivot high/low regression channels
     - Signal score badge
     - Up/down trend arrow
  2. Saves as PNG in the configured output directory.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, List

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from trend_scanner.config import CFG, ChartConfig
from trend_scanner.engine.trend_engine import TrendResult
from trend_scanner.engine.pivots import get_pivots, pivot_prices


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_chart(
    df: pd.DataFrame,
    result: TrendResult,
    timeframe: str = "1h",
    chart_cfg: ChartConfig = None,
) -> Optional[str]:
    """
    Generate and save an annotated candlestick chart for a TrendResult.

    Parameters
    ----------
    df        : Full OHLCV DataFrame (the analysis window data)
    result    : TrendResult from the trend engine
    timeframe : Timeframe label for filename
    chart_cfg : ChartConfig (uses CFG.chart if None)

    Returns
    -------
    str — absolute path to saved PNG, or None on failure
    """
    if df is None or len(df) < 5:
        return None

    cfg = chart_cfg or CFG.chart

    # Limit to exactly what the engine analyzed
    window = result.candles_analyzed if result.candles_analyzed > 0 else min(CFG.trend.analysis_window, len(df))
    plot_df = df.iloc[-window:].reset_index(drop=True)

    try:
        path = _draw_trend_chart(plot_df, result, timeframe, cfg)
        return path
    except Exception as e:
        print(f"  [WARN] Chart generation failed for {result.ticker}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# CORE DRAWING
# ─────────────────────────────────────────────────────────────────────────────

def _draw_trend_chart(
    df: pd.DataFrame,
    result: TrendResult,
    timeframe: str,
    cfg: ChartConfig,
) -> str:
    """Draw the full annotated chart and return save path."""

    fig, (ax_main, ax_vol) = plt.subplots(
        2, 1,
        figsize=cfg.figsize_1h,
        facecolor=cfg.bg,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
    )

    for ax in (ax_main, ax_vol):
        ax.set_facecolor(cfg.panel)
        ax.tick_params(colors=cfg.subtext, labelsize=6.5)
        for spine in ax.spines.values():
            spine.set_color(cfg.grid)
        ax.grid(True, color=cfg.grid, linewidth=0.35, alpha=0.7, zorder=0)

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

    # ── Draw candlesticks ────────────────────────────────────────────────────
    _draw_candles(ax_main, df, xs, cfg)

    # ── Volume bars ──────────────────────────────────────────────────────────
    _draw_volume(ax_vol, df, xs, cfg)

    # ── Linear regression trendline ──────────────────────────────────────────
    _draw_regression_line(ax_main, df, xs, result, cfg)

    # ── Pivot channel lines ──────────────────────────────────────────────────
    _draw_pivot_channels(ax_main, df, xs, cfg)

    # ── Pivot markers ────────────────────────────────────────────────────────
    _draw_pivot_markers(ax_main, df, xs, cfg)

    # ── Signal scorecard ─────────────────────────────────────────────────────
    _draw_signal_scorecard(ax_main, result, cfg)

    # ── Trend annotation arrow ───────────────────────────────────────────────
    _draw_trend_arrow(ax_main, df, xs, result, cfg)

    # ── Price limits ─────────────────────────────────────────────────────────
    price_min = float(df["low"].min())
    price_max = float(df["high"].max())
    pr = price_max - price_min
    ax_main.set_ylim(price_min - pr * 0.05, price_max + pr * 0.25)
    ax_main.set_xlim(xs[0] - (xs[-1] - xs[0]) * 0.01, xs[-1] + (xs[-1] - xs[0]) * 0.01)
    ax_vol.set_xlim(ax_main.get_xlim())

    # ── Title ────────────────────────────────────────────────────────────────
    _draw_title(fig, result, timeframe, len(df), cfg)

    # ── VLM badge (if available) ─────────────────────────────────────────────
    if result.vlm_verdict:
        _draw_vlm_badge(ax_main, result, cfg)

    # ── Hide x-axis top pane ─────────────────────────────────────────────────
    ax_main.set_xticklabels([])

    # ── Save ─────────────────────────────────────────────────────────────────
    os.makedirs(cfg.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    direction_tag = result.direction.upper()
    fname = f"{result.ticker.replace('/', '_')}_{direction_tag}.png"
    save_path = os.path.join(cfg.output_dir, fname)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(save_path, dpi=cfg.dpi, bbox_inches="tight", facecolor=cfg.bg)
    plt.close(fig)

    return os.path.abspath(save_path)


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

    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values

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
    """Draw volume bars."""
    if "volume" not in df.columns:
        return
    n = len(df)
    if n < 2:
        return

    width = (xs[-1] - xs[0]) / n * 0.7
    vols  = df["volume"].values
    opens = df["open"].values
    closes = df["close"].values
    colors = [cfg.bull if c >= o else cfg.bear for o, c in zip(opens, closes)]

    ax.bar(xs, vols, width=width, color=colors, alpha=0.5, zorder=2)
    ax.set_ylabel("Volume", color=cfg.subtext, fontsize=6)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if v >= 1e6 else f"{v:.0f}"))


def _draw_regression_line(ax, df: pd.DataFrame, xs: np.ndarray, result: TrendResult, cfg: ChartConfig):
    """Draw linear regression line over close prices."""
    close = df["close"].values
    x_idx = np.arange(len(close), dtype=np.float64)
    coeffs = np.polyfit(x_idx, close, 1)
    trend_line = np.polyval(coeffs, x_idx)

    color = cfg.up_channel if result.direction == "up" else (
        cfg.dn_channel if result.direction == "down" else cfg.subtext
    )
    ax.plot(xs, trend_line, color=color, linewidth=1.5, linestyle="--",
            alpha=0.75, zorder=5, label="Linear Regression")


def _draw_pivot_channels(ax, df: pd.DataFrame, xs: np.ndarray, cfg: ChartConfig):
    """Draw regression lines fitted on swing highs and swing lows."""
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)

    for bars, col_key, col in [
        (pivot_hi, "high", cfg.pivot_hi),
        (pivot_lo, "low",  cfg.pivot_lo),
    ]:
        if len(bars) < 3:
            continue
        prices = df[col_key].values[bars]
        x_bar  = bars.astype(np.float64)
        coeffs = np.polyfit(x_bar, prices, 1)
        # Extrapolate channel line across full chart
        y_line = np.polyval(coeffs, np.arange(len(df), dtype=np.float64))

        ax.plot(xs, y_line, color=col, linewidth=1.0, linestyle="-.",
                alpha=0.55, zorder=4)


def _draw_pivot_markers(ax, df: pd.DataFrame, xs: np.ndarray, cfg: ChartConfig):
    """Mark pivot highs and lows with small triangles."""
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)

    if len(pivot_hi) > 0:
        ax.scatter(
            xs[pivot_hi], df["high"].values[pivot_hi],
            marker="v", color=cfg.pivot_hi, s=12, zorder=6, alpha=0.75,
        )
    if len(pivot_lo) > 0:
        ax.scatter(
            xs[pivot_lo], df["low"].values[pivot_lo],
            marker="^", color=cfg.pivot_lo, s=12, zorder=6, alpha=0.75,
        )


def _draw_signal_scorecard(ax, result: TrendResult, cfg: ChartConfig):
    """Draw signal pass/fail scorecard in the top-left corner."""
    lines = []
    for sig in result.signals:
        icon = "✓" if sig.passed else "✗"
        color_tag = cfg.signal_ok if sig.passed else cfg.signal_fail
        lines.append((f"{icon} {sig.name}: {sig.score:.0%}", color_tag))

    # Render as a text block — matplotlib doesn't support per-word color easily,
    # so we render each row separately using ax.text with y offset
    transform = ax.transAxes
    y_start = 0.985
    line_h = 0.046

    for i, (text, color) in enumerate(lines):
        ax.text(
            0.01, y_start - i * line_h, text,
            transform=transform, fontsize=7, color=color,
            va="top", ha="left", family="monospace",
            bbox=dict(
                boxstyle="round,pad=0.15",
                facecolor=cfg.bg, edgecolor=color,
                alpha=0.85, linewidth=0.6,
            ),
            zorder=10,
        )


def _draw_trend_arrow(ax, df: pd.DataFrame, xs: np.ndarray, result: TrendResult, cfg: ChartConfig):
    """Draw a large trend arrow in the middle-right of the chart."""
    if result.direction == "none":
        return

    price_min = float(df["low"].min())
    price_max = float(df["high"].max())
    pr = price_max - price_min

    mid_x = xs[int(len(xs) * 0.75)]
    mid_y = price_min + pr * 0.5

    dy = pr * 0.15 if result.direction == "up" else -pr * 0.15
    color = cfg.up_channel if result.direction == "up" else cfg.dn_channel

    ax.annotate(
        "",
        xy=(mid_x, mid_y + dy),
        xytext=(mid_x, mid_y - dy),
        arrowprops=dict(
            arrowstyle="->", color=color, lw=2.5,
            connectionstyle="arc3,rad=0",
        ),
        zorder=8,
    )

    # Direction badge
    label = f"{result.direction_label}  {result.score}/5"
    ax.text(
        mid_x, mid_y + dy * 1.5, label,
        color=color, fontsize=11, fontweight="bold",
        ha="center", va="center", zorder=9,
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor=cfg.bg,
            edgecolor=color,
            linewidth=1.5,
            alpha=0.92,
        ),
    )


def _draw_title(fig, result: TrendResult, timeframe: str, n_bars: int, cfg: ChartConfig):
    """Set figure supertitle."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sig_summary = "  |  ".join(result.signals_passed) if result.signals_passed else "No signals passed"

    fig.suptitle(
        f"{result.emoji}  {result.ticker}  ·  {timeframe}  ·  {result.direction_label}  "
        f"[{result.score}/5  conf={result.confidence:.0%}]"
        f"\nSignals: {sig_summary}   ·   {n_bars} candles   ·   {now}",
        color=cfg.text,
        fontsize=10.5,
        y=0.995,
        fontweight="bold",
    )


def _draw_vlm_badge(ax, result: TrendResult, cfg: ChartConfig):
    """Draw Qwen2.5-VL verification badge in the bottom-right corner."""
    color = cfg.signal_ok if result.vlm_verdict in ("uptrend", "downtrend") else cfg.subtext
    text = (
        f"🤖 VLM: {result.vlm_verdict or 'N/A'}"
        + (f"  {result.vlm_confidence:.0%}" if result.vlm_confidence else "")
    )
    ax.text(
        0.99, 0.02, text,
        transform=ax.transAxes,
        fontsize=7.5, color=color,
        va="bottom", ha="right",
        bbox=dict(
            boxstyle="round,pad=0.3",
            facecolor=cfg.bg, edgecolor=color,
            alpha=0.9, linewidth=0.8,
        ),
        zorder=10,
    )
