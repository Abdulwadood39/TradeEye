"""
normalizer.py — Clean and normalize raw OHLCV DataFrames into a standard schema.

Standard output schema:
    datetime  : pd.Timestamp (UTC, tz-naive)
    open      : float64
    high      : float64
    low       : float64
    close     : float64
    volume    : float64
Integer range index (0-based bar numbers).
"""
from __future__ import annotations

import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


def normalize(raw: pd.DataFrame, source: str = "yfinance") -> pd.DataFrame | None:
    """
    Normalize a raw OHLCV DataFrame from yfinance or CCXT into the standard schema.

    Parameters
    ----------
    raw    : Raw DataFrame (may have MultiIndex columns, mixed case, etc.)
    source : 'yfinance' | 'ccxt'

    Returns
    -------
    Cleaned pd.DataFrame or None if empty / irrecoverable
    """
    if raw is None or raw.empty:
        return None

    if source == "ccxt":
        return _normalize_ccxt(raw)
    else:
        return _normalize_yfinance(raw)


# ─────────────────────────────────────────────────────────────────────────────
# yfinance normalizer
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_yfinance(raw: pd.DataFrame) -> pd.DataFrame | None:
    # Flatten MultiIndex columns (yfinance sometimes returns MultiIndex)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [col[0].lower() for col in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]

    # Keep only OHLCV
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in raw.columns]
    df = raw[keep].copy()

    if df.empty:
        return None

    # Convert timezone-aware index → UTC → naive
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)

    # Move index → 'datetime' column
    df.index.name = "datetime"
    df = df.reset_index()
    if "index" in df.columns:
        df = df.rename(columns={"index": "datetime"})

    df["datetime"] = pd.to_datetime(df["datetime"])

    # Drop rows with any NaN in OHLC
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    if len(df) < 10:
        return None

    return df


# ─────────────────────────────────────────────────────────────────────────────
# CCXT normalizer
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_ccxt(raw: pd.DataFrame) -> pd.DataFrame | None:
    """
    CCXT returns a DataFrame with columns:
        timestamp (ms int), open, high, low, close, volume
    OR already a pre-constructed DataFrame — we handle both.
    """
    df = raw.copy()

    # If given raw OHLCV list rows → columns
    if isinstance(df, list):
        df = pd.DataFrame(df, columns=["timestamp", "open", "high", "low", "close", "volume"])

    # Rename timestamp → datetime
    if "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
        df = df.drop(columns=["timestamp"])
    elif df.index.name == "timestamp":
        df["datetime"] = pd.to_datetime(df.index, unit="ms", utc=True).dt.tz_localize(None)
        df = df.reset_index(drop=True)

    # Lowercase column names
    df.columns = [c.lower() for c in df.columns]

    # Keep only what we need
    keep = ["datetime", "open", "high", "low", "close", "volume"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()

    # Ensure datetime column exists
    if "datetime" not in df.columns:
        return None

    df["datetime"] = pd.to_datetime(df["datetime"])

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    if len(df) < 10:
        return None

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Utility: slice the last N candles
# ─────────────────────────────────────────────────────────────────────────────

def slice_last_n(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Return the last `n` rows of the DataFrame, reset index."""
    if df is None or len(df) == 0:
        return df
    return df.iloc[-n:].reset_index(drop=True)
