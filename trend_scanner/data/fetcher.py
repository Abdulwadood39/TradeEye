"""
fetcher.py — Unified live OHLCV data fetcher.

Routing logic:
  • Crypto tickers (in YFINANCE_TO_CCXT map OR containing '/') → CCXT / Binance public
  • Everything else (stocks, ETFs, commodities, forex) → yfinance

Supports fetching 2000–3000+ candles across 1h and 1d timeframes.
"""
from __future__ import annotations

import time
import warnings
from typing import Optional, List, Dict

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Lazy imports — we only import what's available
try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False

try:
    import ccxt
    _HAS_CCXT = True
except ImportError:
    _HAS_CCXT = False

from trend_scanner.data.normalizer import normalize, slice_last_n
from trend_scanner.config import CFG, YFINANCE_TO_CCXT


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def fetch(
    ticker: str,
    timeframe: str = "1h",
    n_candles: int = 2000,
) -> Optional[pd.DataFrame]:
    """
    Fetch the last `n_candles` of OHLCV data for `ticker` at `timeframe`.

    Parameters
    ----------
    ticker    : Ticker string. Stocks: 'AAPL', 'MSFT', GC=F (gold).
                Crypto: 'BTC-USD', 'BTC/USDT', 'ETH-USD', etc.
    timeframe : '1m', '5m', '15m', '1h', '4h', '1d'
    n_candles : Target number of candles to return

    Returns
    -------
    pd.DataFrame with [datetime, open, high, low, close, volume] or None on failure
    """
    is_crypto = _is_crypto(ticker)

    if is_crypto:
        df = _fetch_ccxt(ticker, timeframe, n_candles)
    else:
        df = _fetch_yfinance(ticker, timeframe, n_candles)

    if df is None or len(df) == 0:
        return None

    # Return exactly the last n_candles
    return slice_last_n(df, n_candles)


def fetch_all(
    tickers: List[str],
    timeframes: List[str] = None,
    n_candles: int = 2000,
) -> Dict[str, Dict[str, Optional[pd.DataFrame]]]:
    """
    Fetch data for multiple tickers and timeframes.

    Returns
    -------
    dict: { ticker: { timeframe: DataFrame } }
    """
    if timeframes is None:
        timeframes = CFG.data.timeframes

    results: Dict[str, Dict[str, Optional[pd.DataFrame]]] = {}

    for ticker in tickers:
        results[ticker] = {}
        for tf in timeframes:
            df = fetch(ticker, tf, n_candles)
            results[ticker][tf] = df
            time.sleep(CFG.data.ticker_sleep)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _is_crypto(ticker: str) -> bool:
    """Return True if ticker should be fetched via CCXT."""
    if "/" in ticker:
        return True
    if ticker.upper() in YFINANCE_TO_CCXT:
        return True
    # Common crypto suffixes
    if ticker.upper().endswith("-USD") and any(
        ticker.upper().startswith(c)
        for c in ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE",
                  "AVAX", "DOT", "MATIC", "LINK", "LTC", "UNI", "ATOM", "XLM"]
    ):
        return True
    return False


def _yf_interval(timeframe: str) -> str:
    """Convert generic timeframe string to yfinance interval string."""
    mapping = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h",
        "1d": "1d", "1w": "1wk", "1M": "1mo",
    }
    return mapping.get(timeframe, timeframe)


def _ccxt_timeframe(timeframe: str) -> str:
    """Convert generic timeframe string to CCXT timeframe string."""
    mapping = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h",
        "1d": "1d", "1w": "1w",
    }
    return mapping.get(timeframe, timeframe)


def _to_ccxt_symbol(ticker: str) -> str:
    """Convert yfinance-style ticker to CCXT symbol (BTC-USD → BTC/USDT)."""
    up = ticker.upper()
    if up in YFINANCE_TO_CCXT:
        return YFINANCE_TO_CCXT[up]
    if "/" in ticker:
        return ticker
    # Fallback: strip -USD and add /USDT
    if up.endswith("-USD"):
        base = up[:-4]
        return f"{base}/USDT"
    return ticker


# ─────────────────────────────────────────────────────────────────────────────
# yfinance FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def _yf_period_for_tf(timeframe: str, n_candles: int) -> str:
    """
    Calculate a yfinance period string that will definitely contain n_candles.
    yfinance limits: 1m=7d, 2m-30m=60d, 1h=730d (2y), 1d=unlimited.
    """
    tf = timeframe.lower()
    if tf == "1m":
        return "7d"
    if tf in ("2m", "5m", "15m", "30m"):
        return "60d"
    if tf in ("1h", "2h", "4h"):
        return "2y"   # ~17,520 hourly bars — plenty for 3000
    if tf == "1d":
        # n_candles days ÷ 250 trading days per year → round up to years
        years = max(1, (n_candles // 250) + 1)
        return f"{min(years, 10)}y"
    return "2y"


def _fetch_yfinance(
    ticker: str,
    timeframe: str,
    n_candles: int,
    retries: int = None,
) -> Optional[pd.DataFrame]:
    if not _HAS_YFINANCE:
        print("  [ERR] yfinance not installed. Run: pip install yfinance")
        return None

    retries = retries or CFG.data.max_retries
    interval = _yf_interval(timeframe)
    period = _yf_period_for_tf(timeframe, n_candles)

    for attempt in range(retries):
        try:
            raw = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                repair=True,
            )
            if raw is None or raw.empty:
                print(f"  [WARN] yfinance: No data for {ticker} {timeframe}")
                return None

            df = normalize(raw, source="yfinance")
            if df is not None and len(df) > 0:
                print(f"  [OK] {ticker} {timeframe} via yfinance: {len(df)} bars")
                return df

        except Exception as e:
            print(f"  [ERR] yfinance {ticker} {timeframe} (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(CFG.data.retry_delay)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# CCXT FETCHER
# ─────────────────────────────────────────────────────────────────────────────

# Module-level exchange instance (lazy init, reuse for all requests)
_ccxt_exchange = None

def _get_exchange():
    global _ccxt_exchange
    if _ccxt_exchange is None:
        if not _HAS_CCXT:
            return None
        exchange_class = getattr(ccxt, CFG.data.ccxt_exchange)
        _ccxt_exchange = exchange_class({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
    return _ccxt_exchange


def _fetch_ccxt(
    ticker: str,
    timeframe: str,
    n_candles: int,
    retries: int = None,
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV from CCXT (Binance public API — no key needed).
    Paginates automatically to reach n_candles.
    """
    if not _HAS_CCXT:
        print("  [ERR] ccxt not installed. Run: pip install ccxt")
        return None

    exchange = _get_exchange()
    if exchange is None:
        return None

    symbol = _to_ccxt_symbol(ticker)
    tf = _ccxt_timeframe(timeframe)
    retries = retries or CFG.data.max_retries

    # Binance max per request = 1000 candles
    batch_size = 1000
    all_ohlcv: List[list] = []

    # Start timestamp: go far enough back to get n_candles
    tf_ms = _tf_to_ms(tf)
    since_ms = exchange.milliseconds() - (n_candles + 100) * tf_ms

    for attempt in range(retries):
        try:
            if not exchange.has.get("fetchOHLCV", False):
                print(f"  [ERR] {CFG.data.ccxt_exchange} does not support fetchOHLCV")
                return None

            all_ohlcv = []
            since = since_ms

            while len(all_ohlcv) < n_candles:
                batch = exchange.fetch_ohlcv(
                    symbol, tf, since=since, limit=batch_size
                )
                if not batch:
                    break
                all_ohlcv.extend(batch)
                since = batch[-1][0] + 1
                if len(batch) < batch_size:
                    break  # reached current time
                time.sleep(exchange.rateLimit / 1000)

            if not all_ohlcv:
                print(f"  [WARN] CCXT: No data for {symbol} {tf}")
                return None

            df = pd.DataFrame(
                all_ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df = normalize(df, source="ccxt")
            if df is not None and len(df) > 0:
                print(f"  [OK] {ticker} ({symbol}) {tf} via CCXT: {len(df)} bars")
                return df

        except Exception as e:
            print(f"  [ERR] CCXT {symbol} {tf} (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(CFG.data.retry_delay)
                _ccxt_exchange = None  # reset exchange on error

    return None


def _tf_to_ms(tf: str) -> int:
    """Convert CCXT timeframe string to milliseconds."""
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
    try:
        num = int(tf[:-1])
        unit = tf[-1]
        return num * units.get(unit, 3_600_000)
    except Exception:
        return 3_600_000   # default 1h
