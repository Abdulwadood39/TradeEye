"""
signals.py — Trend-detection signal suite (v2).

7 signals total:
  Core (scored):
    1. Linear Regression Slope       — direction + speed
    2. Mann-Kendall Test             — statistical monotonicity
    3. ADX                           — trend strength
    4. Market Structure (HH/HL)      — pivot structure
    5. Pivot Channel                 — channel direction

  Hard Veto (must pass, not scored):
    V1. R² Linearity Gate            — rejects noisy sideways drift
    V2. ATR Consolidation Filter     — rejects choppy range-bound markets
    V3. Trend Break Detector         — rejects trends that have structurally broken

A trend is ONLY declared when:
  - ≥ min_signals_for_trend core signals agree on the same direction
  - ALL three hard veto signals pass
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Tuple

import numpy as np
import pandas as pd

from trend_scanner.config import CFG
from trend_scanner.engine.pivots import (
    get_pivots, pivot_prices,
    regression_slope_on_pivots, hh_hl_ratio,
)


@dataclass
class SignalResult:
    name: str
    passed: bool
    direction: str      # 'up' | 'down' | 'none'
    score: float        # 0.0–1.0
    is_veto: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 1 — Linear Regression Slope
# ─────────────────────────────────────────────────────────────────────────────

def signal_linreg_slope(df: pd.DataFrame) -> SignalResult:
    close = df["close"].values.astype(np.float64)
    x = np.arange(len(close), dtype=np.float64)

    coeffs    = np.polyfit(x, close, 1)
    slope_raw = float(coeffs[0])
    mean_price = float(np.mean(close))

    slope_bps = (slope_raw / mean_price * 10_000) if mean_price > 0 else 0.0
    threshold = CFG.trend.slope_min_bps
    passed    = abs(slope_bps) >= threshold
    direction = "up" if slope_bps > 0 else ("down" if slope_bps < 0 else "none")
    score     = min(abs(slope_bps) / (threshold * 5), 1.0) if threshold > 0 else 0.0

    return SignalResult(
        name="LinReg Slope", passed=passed,
        direction=direction if passed else "none",
        score=score,
        detail={"slope_bps": round(slope_bps, 4)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 2 — Mann-Kendall
# ─────────────────────────────────────────────────────────────────────────────

def signal_mann_kendall(df: pd.DataFrame) -> SignalResult:
    close = df["close"].values.astype(np.float64)

    try:
        import pymannkendall as mk
        res       = mk.original_test(close)
        trend_str = res.trend
        p_value   = res.p
        tau       = res.Tau
    except ImportError:
        trend_str, p_value, tau = _manual_mk(close)

    alpha        = CFG.trend.mk_alpha
    is_sig       = p_value < alpha
    direction    = "none"
    if is_sig:
        if "increasing" in str(trend_str):
            direction = "up"
        elif "decreasing" in str(trend_str):
            direction = "down"

    passed = is_sig and direction != "none"
    score  = min(1.0 - p_value, 1.0) if is_sig else 0.0

    return SignalResult(
        name="Mann-Kendall", passed=passed, direction=direction,
        score=score,
        detail={"p_value": round(p_value, 6), "tau": round(float(tau), 4)},
    )


def _manual_mk(data: np.ndarray):
    """Pure-numpy Mann-Kendall (fallback when pymannkendall not installed)."""
    n = len(data)
    # Subsample for speed when n is large (1m timeframe with 500+ bars)
    if n > 300:
        step = max(1, n // 300)
        data = data[::step]
        n = len(data)

    s = int(np.sum([np.sign(data[j] - data[i])
                    for i in range(n - 1)
                    for j in range(i + 1, n)]))
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    if var_s <= 0:
        return "no trend", 1.0, 0.0
    z = (s - 1) / np.sqrt(var_s) if s > 0 else ((s + 1) / np.sqrt(var_s) if s < 0 else 0.0)
    from scipy.stats import norm
    p   = 2 * (1 - norm.cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))
    trend = "no trend"
    if p < 0.05:
        trend = "increasing" if s > 0 else "decreasing"
    return trend, p, tau


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 3 — ADX
# ─────────────────────────────────────────────────────────────────────────────

def signal_adx(df: pd.DataFrame) -> SignalResult:
    period    = CFG.trend.adx_period
    threshold = CFG.trend.adx_threshold

    try:
        import pandas_ta as ta
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=period)
        if adx_df is None or adx_df.empty:
            raise ValueError
        adx_col = next((c for c in adx_df.columns if c.startswith("ADX")), None)
        dmp_col = next((c for c in adx_df.columns if "DMP" in c), None)
        dmn_col = next((c for c in adx_df.columns if "DMN" in c), None)
        if not all([adx_col, dmp_col, dmn_col]):
            raise ValueError
        adx_val = float(adx_df[adx_col].iloc[-1])
        dmp_val = float(adx_df[dmp_col].iloc[-1])
        dmn_val = float(adx_df[dmn_col].iloc[-1])
    except Exception:
        adx_val, dmp_val, dmn_val = _manual_adx(
            df["high"].values, df["low"].values, df["close"].values, period
        )

    passed    = adx_val >= threshold and not np.isnan(adx_val)
    direction = "none"
    if passed:
        direction = "up" if dmp_val > dmn_val else "down"

    score = min(adx_val / 50.0, 1.0)

    return SignalResult(
        name="ADX", passed=passed, direction=direction, score=score,
        detail={"adx": round(adx_val, 2), "+di": round(dmp_val, 2), "-di": round(dmn_val, 2)},
    )


def _manual_adx(high, low, close, period=14):
    n = len(high)
    if n < period + 1:
        return 0.0, 0.0, 0.0
    tr = np.zeros(n); dm_pos = np.zeros(n); dm_neg = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
        up = high[i]-high[i-1]; dn = low[i-1]-low[i]
        dm_pos[i] = up if (up > dn and up > 0) else 0.0
        dm_neg[i] = dn if (dn > up and dn > 0) else 0.0

    def smooth(a, p):
        out = np.zeros(n); out[p] = np.sum(a[1:p+1])
        for i in range(p+1, n): out[i] = out[i-1] - out[i-1]/p + a[i]
        return out

    atr = smooth(tr, period); sdmp = smooth(dm_pos, period); sdmn = smooth(dm_neg, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        dip = np.where(atr > 0, 100*sdmp/atr, 0.0)
        din = np.where(atr > 0, 100*sdmn/atr, 0.0)
        dx  = np.where((dip+din) > 0, 100*np.abs(dip-din)/(dip+din), 0.0)
    adx = np.zeros(n)
    if 2*period-1 < n:
        adx[2*period-1] = np.mean(dx[period:2*period])
        for i in range(2*period, n): adx[i] = (adx[i-1]*(period-1)+dx[i])/period
    return float(adx[-1]), float(dip[-1]), float(din[-1])


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 4 — Market Structure (HH/HL or LH/LL)
# ─────────────────────────────────────────────────────────────────────────────

def signal_market_structure(df: pd.DataFrame) -> SignalResult:
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)

    if len(pivot_hi) < 3 or len(pivot_lo) < 3:
        return SignalResult(
            name="Market Structure", passed=False, direction="none", score=0.0,
            detail={"pivot_highs": len(pivot_hi), "pivot_lows": len(pivot_lo)},
        )

    ratio, direction = hh_hl_ratio(
        df["high"].values, df["low"].values, pivot_hi, pivot_lo
    )

    threshold = CFG.trend.hh_hl_min_ratio
    passed    = ratio >= threshold and direction != "none"
    score     = min(ratio, 1.0)

    return SignalResult(
        name="Market Structure", passed=passed,
        direction=direction if passed else "none",
        score=score,
        detail={"hh_hl_ratio": round(ratio, 3), "n_pivots_hi": len(pivot_hi), "n_pivots_lo": len(pivot_lo)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 5 — Pivot Channel
# ─────────────────────────────────────────────────────────────────────────────

def signal_pivot_channel(df: pd.DataFrame) -> SignalResult:
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)

    hi_prices = pivot_prices(df["high"].values, pivot_hi)
    lo_prices = pivot_prices(df["low"].values, pivot_lo)
    hi_slope  = regression_slope_on_pivots(hi_prices, pivot_hi)
    lo_slope  = regression_slope_on_pivots(lo_prices, pivot_lo)

    th = CFG.trend.channel_slope_min_bps

    if hi_slope > th and lo_slope > th:
        direction = "up"; passed = True
    elif hi_slope < -th and lo_slope < -th:
        direction = "down"; passed = True
    else:
        direction = "none"; passed = False

    score = min((abs(hi_slope) + abs(lo_slope)) / (2 * th * 5), 1.0) if passed else 0.0

    return SignalResult(
        name="Pivot Channel", passed=passed, direction=direction, score=score,
        detail={"hi_channel_bps": round(hi_slope, 4), "lo_channel_bps": round(lo_slope, 4)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# VETO V1 — R² Linearity Gate
# Rejects noisy sideways drift that a slope signal can mistake for a trend
# ─────────────────────────────────────────────────────────────────────────────

def veto_r2_linearity(df: pd.DataFrame) -> SignalResult:
    """
    Compute R² of close prices vs linear regression.
    R² < threshold → market is noisy/choppy, not a clean directional trend.
    A genuine strong trend has R² > 0.45; sideways chop is usually < 0.20.
    """
    close = df["close"].values.astype(np.float64)
    x     = np.arange(len(close), dtype=np.float64)

    coeffs   = np.polyfit(x, close, 1)
    y_fit    = np.polyval(coeffs, x)
    ss_res   = np.sum((close - y_fit) ** 2)
    ss_tot   = np.sum((close - np.mean(close)) ** 2)
    r2       = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    threshold = CFG.trend.r2_min_threshold
    passed    = r2 >= threshold
    score     = float(r2)

    # Direction matches sign of slope (needed for consistent reporting)
    slope = float(coeffs[0])
    direction = "up" if slope > 0 else "down"

    return SignalResult(
        name="R² Linearity", passed=passed, direction=direction,
        score=score, is_veto=True,
        detail={"r2": round(r2, 4), "threshold": threshold},
    )


# ─────────────────────────────────────────────────────────────────────────────
# VETO V2 — ATR Consolidation Filter
# Rejects markets where candle range >> net directional move (= choppy)
# ─────────────────────────────────────────────────────────────────────────────

def veto_atr_consolidation(df: pd.DataFrame) -> SignalResult:
    """
    Computes: net_move / (mean_ATR × n_candles)
    If this ratio is too low the market is chopping without going anywhere.
    Example: net_move=50pts, ATR=20pts/bar, 200 bars → ratio=50/(20×200)=0.0125 → SIDEWAYS
    """
    close  = df["close"].values.astype(np.float64)
    high   = df["high"].values.astype(np.float64)
    low    = df["low"].values.astype(np.float64)
    n      = len(close)

    # True Range
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
    )
    mean_atr = float(np.mean(tr)) if len(tr) > 0 else 1e-9

    # Net directional move
    net_move = abs(float(close[-1]) - float(close[0]))

    # Normalise: how much of the "potential" move was directional?
    denominator = mean_atr * n
    ratio = net_move / denominator if denominator > 0 else 0.0

    threshold = CFG.trend.atr_move_ratio_min
    passed    = ratio >= threshold
    score     = min(ratio / (threshold * 5), 1.0)
    direction = "up" if close[-1] > close[0] else "down"

    return SignalResult(
        name="ATR Filter", passed=passed, direction=direction,
        score=score, is_veto=True,
        detail={
            "net_move_ratio": round(ratio, 4),
            "mean_atr":       round(mean_atr, 4),
            "net_move":       round(net_move, 4),
            "threshold":      threshold,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# VETO V3 — Trend Break Detector
# Rejects trends where price has broken the support/resistance channel
# ─────────────────────────────────────────────────────────────────────────────

def veto_trend_break(df: pd.DataFrame, direction: str) -> SignalResult:
    """
    For an uptrend: checks that close never closes below the ascending
    support trendline (fitted through swing lows) by more than a tolerance.

    For a downtrend: checks that close never closes above the descending
    resistance trendline (fitted through swing highs) by more than tolerance.

    If the trend has broken structurally in the last 20% of bars → veto.
    """
    if direction == "none":
        return SignalResult(
            name="Trend Break", passed=True, direction="none",
            score=1.0, is_veto=True,
            detail={"reason": "no direction to check"},
        )

    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)
    n = len(df)
    close = df["close"].values.astype(np.float64)
    mean_price = float(np.mean(close))

    # Look at last 20% of bars for recent breaks
    check_from = int(n * 0.80)

    if direction == "up":
        if len(pivot_lo) < 3:
            # Not enough pivots to draw a trendline — benefit of the doubt
            return SignalResult(
                name="Trend Break", passed=True, direction=direction,
                score=0.8, is_veto=True,
                detail={"reason": "insufficient pivots"},
            )
        lo_prices = df["low"].values[pivot_lo].astype(np.float64)
        coeffs    = np.polyfit(pivot_lo.astype(float), lo_prices, 1)
        # Tolerance: 1.5% below trendline = break
        tolerance = mean_price * 0.015
        broken_bars = 0
        for i in range(check_from, n):
            tl_val = np.polyval(coeffs, float(i))
            if close[i] < tl_val - tolerance:
                broken_bars += 1
        # If more than 3 bars broke below support → trend is broken
        passed = broken_bars <= 3

    else:  # down
        if len(pivot_hi) < 3:
            return SignalResult(
                name="Trend Break", passed=True, direction=direction,
                score=0.8, is_veto=True,
                detail={"reason": "insufficient pivots"},
            )
        hi_prices = df["high"].values[pivot_hi].astype(np.float64)
        coeffs    = np.polyfit(pivot_hi.astype(float), hi_prices, 1)
        tolerance = mean_price * 0.015
        broken_bars = 0
        for i in range(check_from, n):
            tl_val = np.polyval(coeffs, float(i))
            if close[i] > tl_val + tolerance:
                broken_bars += 1
        passed = broken_bars <= 3

    score = 1.0 if passed else 0.0
    check_n = n - check_from

    return SignalResult(
        name="Trend Break", passed=passed, direction=direction,
        score=score, is_veto=True,
        detail={"broken_bars": broken_bars, "checked_bars": check_n},
    )
