"""
pivots.py — Swing pivot detection for the trend engine.

Finds local highs and lows using scipy argrelextrema, with
lightweight peak significance filtering to avoid detecting noise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from typing import Tuple


def find_pivot_highs(high: np.ndarray, order: int = 5) -> np.ndarray:
    """
    Detect local HIGH pivot bar indices.

    Parameters
    ----------
    high  : np.ndarray of high prices
    order : number of bars each side required to confirm pivot

    Returns
    -------
    np.ndarray of int bar indices
    """
    return argrelextrema(high, np.greater_equal, order=order)[0]


def find_pivot_lows(low: np.ndarray, order: int = 5) -> np.ndarray:
    """
    Detect local LOW pivot bar indices.

    Parameters
    ----------
    low   : np.ndarray of low prices
    order : number of bars each side required to confirm pivot

    Returns
    -------
    np.ndarray of int bar indices
    """
    return argrelextrema(low, np.less_equal, order=order)[0]


def get_pivots(df: pd.DataFrame, order: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    """
    Get both pivot high and pivot low bar indices from a DataFrame.

    Parameters
    ----------
    df    : DataFrame with 'high' and 'low' columns
    order : pivot detection sensitivity

    Returns
    -------
    (pivot_high_bars, pivot_low_bars) — arrays of int indices
    """
    high = df["high"].values
    low = df["low"].values
    return find_pivot_highs(high, order), find_pivot_lows(low, order)


def pivot_prices(arr: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Return the price values at the given index positions."""
    return arr[indices]


def regression_slope_on_pivots(
    prices: np.ndarray,
    indices: np.ndarray,
    normalize_by_mean: bool = True,
) -> float:
    """
    Fit a linear regression over pivot prices and return the slope.
    If normalize_by_mean=True → return slope as basis points per bar.

    Returns 0.0 if fewer than 3 pivots available.
    """
    if len(indices) < 3:
        return 0.0

    x = indices.astype(np.float64)
    y = prices.astype(np.float64)
    slope = float(np.polyfit(x, y, 1)[0])

    if normalize_by_mean:
        mean_price = float(np.mean(y))
        if mean_price > 0:
            slope = (slope / mean_price) * 10_000  # convert to bps per bar

    return slope


def hh_hl_ratio(
    high: np.ndarray,
    low: np.ndarray,
    pivot_hi_bars: np.ndarray,
    pivot_lo_bars: np.ndarray,
) -> Tuple[float, str]:
    """
    Compute the fraction of consecutive swing highs that are Higher Highs
    AND consecutive swing lows that are Higher Lows.

    Returns
    -------
    (ratio, direction):
        ratio     : float 0.0–1.0 (fraction of qualifying pairs)
        direction : 'up' | 'down' | 'none'
    """
    hi_prices = high[pivot_hi_bars]
    lo_prices = low[pivot_lo_bars]

    # Count consecutive HH pairs
    hh_count = sum(hi_prices[i] > hi_prices[i-1] for i in range(1, len(hi_prices)))
    lh_count = sum(hi_prices[i] < hi_prices[i-1] for i in range(1, len(hi_prices)))

    # Count consecutive HL pairs
    hl_count = sum(lo_prices[i] > lo_prices[i-1] for i in range(1, len(lo_prices)))
    ll_count = sum(lo_prices[i] < lo_prices[i-1] for i in range(1, len(lo_prices)))

    total_hi = max(len(hi_prices) - 1, 1)
    total_lo = max(len(lo_prices) - 1, 1)

    hh_ratio = hh_count / total_hi
    ll_ratio = ll_count / total_lo
    lh_ratio = lh_count / total_hi
    hl_ratio = hl_count / total_lo

    up_ratio   = (hh_ratio + hl_ratio) / 2
    down_ratio = (lh_ratio + ll_ratio) / 2

    if up_ratio > down_ratio:
        return up_ratio, "up"
    elif down_ratio > up_ratio:
        return down_ratio, "down"
    else:
        return 0.0, "none"
