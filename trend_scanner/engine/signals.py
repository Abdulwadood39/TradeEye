"""
signals.py — Five independent trend-detection signals.

Each signal function returns a SignalResult with:
  passed    : bool
  direction : 'up' | 'down' | 'none'
  score     : float (confidence within the signal, 0.0–1.0)
  detail    : dict with raw values for charting / logging
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional

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
    direction: str          # 'up' | 'down' | 'none'
    score: float            # 0.0 – 1.0
    detail: Dict[str, Any] = field(default_factory=dict)
    is_veto: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 1 — Linear Regression Slope
# ─────────────────────────────────────────────────────────────────────────────

def signal_linreg_slope(df: pd.DataFrame) -> SignalResult:
    """
    Fit a linear regression on close prices.
    Slope normalized to basis points per candle.
    """
    close = df["close"].values.astype(np.float64)
    x = np.arange(len(close), dtype=np.float64)

    slope_raw = float(np.polyfit(x, close, 1)[0])
    mean_price = float(np.mean(close))

    # Normalise to basis points per candle
    slope_bps = (slope_raw / mean_price * 10_000) if mean_price > 0 else 0.0

    threshold = CFG.trend.slope_min_bps
    passed = abs(slope_bps) >= threshold
    direction = "up" if slope_bps > 0 else ("down" if slope_bps < 0 else "none")

    # Score: how far the slope exceeds the threshold (capped at 1.0)
    score = min(abs(slope_bps) / (threshold * 5), 1.0) if threshold > 0 else 0.0

    return SignalResult(
        name="LinReg Slope",
        passed=passed,
        direction=direction if passed else "none",
        score=score,
        detail={"slope_bps": round(slope_bps, 4), "slope_raw": round(slope_raw, 6)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 2 — Mann-Kendall Trend Test
# ─────────────────────────────────────────────────────────────────────────────

def signal_mann_kendall(df: pd.DataFrame) -> SignalResult:
    """
    Non-parametric Mann-Kendall test for monotonic trend.
    Uses pymannkendall library if available, falls back to custom implementation.
    """
    close = df["close"].values.astype(np.float64)

    if len(close) > 300:
        # Subsample to 150 evenly spaced points to avoid over-powered p-values
        idx = np.linspace(0, len(close) - 1, 150, dtype=int)
        close = close[idx]

    try:
        import pymannkendall as mk
        result = mk.original_test(close)
        trend_str = result.trend    # 'increasing' | 'decreasing' | 'no trend'
        p_value = result.p
        tau = result.Tau
    except ImportError:
        # Fallback: manual Mann-Kendall
        trend_str, p_value, tau = _manual_mann_kendall(close)

    alpha = CFG.trend.mk_alpha
    is_significant = p_value < alpha

    direction = "none"
    if is_significant:
        if "increasing" in trend_str or (isinstance(trend_str, str) and trend_str == "up"):
            direction = "up"
        elif "decreasing" in trend_str or (isinstance(trend_str, str) and trend_str == "down"):
            direction = "down"

    TAU_MIN = 0.25
    passed = is_significant and direction != "none" and abs(float(tau)) >= TAU_MIN

    # Score based on how far below alpha the p-value is (stronger = lower p)
    score = min(1.0 - p_value, 1.0) if is_significant else 0.0

    return SignalResult(
        name="Mann-Kendall",
        passed=passed,
        direction=direction,
        score=score,
        detail={"p_value": round(p_value, 6), "tau": round(float(tau), 4), "trend": trend_str},
    )


def _manual_mann_kendall(data: np.ndarray):
    """Lightweight Mann-Kendall implementation (no external dependency)."""
    n = len(data)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = data[j] - data[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    # Variance of S
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    if var_s <= 0:
        return "no trend", 1.0, 0.0

    # Z statistic
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0

    # Two-tailed p-value using normal approximation
    from scipy.stats import norm
    p = 2 * (1 - norm.cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))

    trend = "no trend"
    if p < 0.05:
        trend = "increasing" if s > 0 else "decreasing"

    return trend, p, tau


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 3 — ADX (Average Directional Index)
# ─────────────────────────────────────────────────────────────────────────────

def signal_adx(df: pd.DataFrame) -> SignalResult:
    """
    ADX measures trend strength (direction-neutral).
    +DI > -DI → uptrend; -DI > +DI → downtrend.
    """
    period = CFG.trend.adx_period
    threshold = CFG.trend.adx_threshold

    try:
        import pandas_ta as ta
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=period)
        if adx_df is None or adx_df.empty:
            raise ValueError("pandas_ta returned empty ADX")

        adx_col  = f"ADX_{period}"
        dmp_col  = f"DMP_{period}"
        dmn_col  = f"DMN_{period}"

        if adx_col not in adx_df.columns:
            # Try alternative column names
            adx_col  = [c for c in adx_df.columns if c.startswith("ADX")][0]
            dmp_col  = [c for c in adx_df.columns if "DMP" in c or "+DI" in c][0]
            dmn_col  = [c for c in adx_df.columns if "DMN" in c or "-DI" in c][0]

        adx_val = float(adx_df[adx_col].iloc[-1])
        dmp_val = float(adx_df[dmp_col].iloc[-1])
        dmn_val = float(adx_df[dmn_col].iloc[-1])

    except Exception:
        # Manual ADX calculation fallback
        adx_val, dmp_val, dmn_val = _manual_adx(
            df["high"].values, df["low"].values, df["close"].values, period
        )

    passed = adx_val >= threshold and not (np.isnan(adx_val))
    direction = "none"
    if passed:
        if dmp_val > dmn_val:
            direction = "up"
        elif dmn_val > dmp_val:
            direction = "down"

    score = min(adx_val / 50.0, 1.0)  # ADX 50 = max score

    return SignalResult(
        name="ADX",
        passed=passed,
        direction=direction,
        score=score,
        detail={
            "adx":  round(adx_val, 2),
            "+di":  round(dmp_val, 2),
            "-di":  round(dmn_val, 2),
        },
    )


def _manual_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14):
    """Pure-numpy ADX calculation."""
    n = len(high)
    if n < period + 1:
        return 0.0, 0.0, 0.0

    tr = np.zeros(n)
    dm_pos = np.zeros(n)
    dm_neg = np.zeros(n)

    for i in range(1, n):
        hl = high[i] - low[i]
        hpc = abs(high[i] - close[i - 1])
        lpc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hpc, lpc)

        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        dm_pos[i] = up if (up > dn and up > 0) else 0.0
        dm_neg[i] = dn if (dn > up and dn > 0) else 0.0

    def smooth(arr, p):
        out = np.zeros(n)
        out[p] = np.sum(arr[1:p+1])
        for i in range(p + 1, n):
            out[i] = out[i-1] - out[i-1]/p + arr[i]
        return out

    atr = smooth(tr, period)
    sdm_pos = smooth(dm_pos, period)
    sdm_neg = smooth(dm_neg, period)

    with np.errstate(divide="ignore", invalid="ignore"):
        di_pos = np.where(atr > 0, 100 * sdm_pos / atr, 0.0)
        di_neg = np.where(atr > 0, 100 * sdm_neg / atr, 0.0)
        dx = np.where((di_pos + di_neg) > 0,
                      100 * np.abs(di_pos - di_neg) / (di_pos + di_neg), 0.0)

    adx_arr = np.zeros(n)
    adx_arr[2*period-1] = np.mean(dx[period:2*period])
    for i in range(2*period, n):
        adx_arr[i] = (adx_arr[i-1] * (period - 1) + dx[i]) / period

    return float(adx_arr[-1]), float(di_pos[-1]), float(di_neg[-1])


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 4 — Higher Highs / Higher Lows (Market Structure)
# ─────────────────────────────────────────────────────────────────────────────

def signal_market_structure(df: pd.DataFrame) -> SignalResult:
    """
    Check that swing pivots form HH+HL (uptrend) or LH+LL (downtrend) structure.
    """
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)

    if len(pivot_hi) < 3 or len(pivot_lo) < 3:
        return SignalResult(
            name="Market Structure (HH/HL)",
            passed=False,
            direction="none",
            score=0.0,
            detail={"pivot_highs": len(pivot_hi), "pivot_lows": len(pivot_lo)},
        )

    ratio, direction = hh_hl_ratio(
        df["high"].values, df["low"].values, pivot_hi, pivot_lo
    )

    threshold = CFG.trend.hh_hl_min_ratio
    passed = ratio >= threshold and direction != "none"
    score = min(ratio, 1.0)

    return SignalResult(
        name="Market Structure (HH/HL)",
        passed=passed,
        direction=direction if passed else "none",
        score=score,
        detail={
            "hh_hl_ratio":  round(ratio, 3),
            "pivot_highs":  int(len(pivot_hi)),
            "pivot_lows":   int(len(pivot_lo)),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 5 — Pivot Regression Channel
# ─────────────────────────────────────────────────────────────────────────────

def signal_pivot_channel(df: pd.DataFrame) -> SignalResult:
    """
    Fit separate linear regressions on swing HIGH pivots and swing LOW pivots.
    Both must slope the same direction for the signal to pass.
    """
    pivot_hi, pivot_lo = get_pivots(df, order=CFG.trend.pivot_order)

    hi_prices = pivot_prices(df["high"].values, pivot_hi)
    lo_prices = pivot_prices(df["low"].values, pivot_lo)

    hi_slope = regression_slope_on_pivots(hi_prices, pivot_hi)
    lo_slope = regression_slope_on_pivots(lo_prices, pivot_lo)

    threshold = CFG.trend.channel_slope_min_bps

    hi_up = hi_slope > threshold
    hi_dn = hi_slope < -threshold
    lo_up = lo_slope > threshold
    lo_dn = lo_slope < -threshold

    if hi_up and lo_up:
        direction = "up"
        passed = True
        score = min((abs(hi_slope) + abs(lo_slope)) / (2 * threshold * 5), 1.0)
    elif hi_dn and lo_dn:
        direction = "down"
        passed = True
        score = min((abs(hi_slope) + abs(lo_slope)) / (2 * threshold * 5), 1.0)
    else:
        direction = "none"
        passed = False
        score = 0.0

    return SignalResult(
        name="Pivot Channel",
        passed=passed,
        direction=direction,
        score=score,
        detail={
            "hi_channel_bps": round(hi_slope, 4),
            "lo_channel_bps": round(lo_slope, 4),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# VETO GATES
# ─────────────────────────────────────────────────────────────────────────────

def veto_r2_linearity(df: pd.DataFrame, min_r2: float = 0.55) -> SignalResult:
    close = df["close"].values
    x = np.arange(len(close), dtype=np.float64)
    slope, intercept = np.polyfit(x, close, 1)
    predicted = slope * x + intercept
    ss_res = np.sum((close - predicted) ** 2)
    ss_tot = np.sum((close - np.mean(close)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    passed = r2 >= min_r2
    return SignalResult(name="R² Linearity", passed=passed, direction="none", 
                        score=r2, detail={"r2": round(r2, 4)}, is_veto=True)

def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(high)
    if n < period + 1:
        return 0.0
    tr = np.zeros(n)
    for i in range(1, n):
        hl = high[i] - low[i]
        hpc = abs(high[i] - close[i - 1])
        lpc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hpc, lpc)
    return float(np.mean(tr[-period:]))

def veto_atr_consolidation(df: pd.DataFrame, period: int = 14, window: int = 250) -> SignalResult:
    recent_df = df.iloc[-window:] if len(df) > window else df
    atr = _compute_atr(recent_df, period)
    close = recent_df["close"].values
    net_move = abs(close[-1] - close[0])
    total_atr = atr * len(recent_df)  # sum of all ATR bars (approx)
    efficiency_ratio = net_move / total_atr if total_atr > 0 else 0.0
    passed = efficiency_ratio >= 0.02
    return SignalResult(name="ATR Efficiency", passed=passed, direction="none",
                        score=efficiency_ratio, detail={"efficiency_ratio": round(efficiency_ratio, 4)},
                        is_veto=True)

def veto_trend_break(df: pd.DataFrame, direction: str, lookback: int = 50) -> SignalResult:
    recent = df.iloc[-lookback:]
    pivot_hi, pivot_lo = get_pivots(recent, order=3)
    passed = True
    if direction == "up" and len(pivot_lo) >= 2:
        lo_prices = recent["low"].values[pivot_lo]
        if lo_prices[-1] < lo_prices[-2]:
            passed = False
    elif direction == "down" and len(pivot_hi) >= 2:
        hi_prices = recent["high"].values[pivot_hi]
        if hi_prices[-1] > hi_prices[-2]:
            passed = False
    return SignalResult(name="Trend Break", passed=passed, direction="none",
                        score=1.0 if passed else 0.0, detail={}, is_veto=True)
