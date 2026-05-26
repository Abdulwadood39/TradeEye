"""
config/tickers.py — Watchlist definitions for the iTrade Trend Scanner.

Edit this file to change which tickers are scanned.
DEFAULT_TICKERS is used when no --tickers flag is passed.
"""
from __future__ import annotations
from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# STOCK WATCHLIST
# ─────────────────────────────────────────────────────────────────────────────

STOCKS_INDEX: List[str] = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'AVGO', 'NFLX',
    'INTC', 'QCOM', 'CSCO', 'ORCL', 'ADBE', 'CRM', 'MU', 'AMAT', 'LRCX', 'KLAC',

    'SMCI', 'ARM', 'ASML', 'TSM', 'SOXX', 'SMH', 'NXPI', 'MRVL', 'ADI', 'MCHP',

    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'SCHW', 'AXP', 'BLK', 'USB',

    'WMT', 'COST', 'HD', 'LOW', 'TGT', 'MCD', 'SBUX', 'NKE', 'CMG', 'TJX',

    'GOOG', 'UBER', 'ABNB', 'SPOT', 'PYPL', 'SHOP', 'SQ', 'PLTR', 'SNOW', 'NET',

    'LLY', 'JNJ', 'UNH', 'ABBV', 'MRK', 'PFE', 'TMO', 'DHR', 'ISRG', 'VRTX',

    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL',

    'CAT', 'DE', 'GE', 'RTX', 'HON', 'UPS', 'FDX', 'UNP', 'ETN', 'PH',

    'SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'XLF', 'XLK', 'XLE', 'XLV', 'XLI',
    'XLY', 'XLP', 'XLU', 'ARKK', 'SOXL', 'TQQQ', 'SQQQ', 'UVXY', 'VXX', 'TLT',
]

# ─────────────────────────────────────────────────────────────────────────────
# FOREX WATCHLIST
# ─────────────────────────────────────────────────────────────────────────────

FOREX_TICKERS: List[str] = [
    # Majors
    'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCHF=X', 'AUDUSD=X', 'NZDUSD=X', 'USDCAD=X',
    # Exotics
    'AUDPLN=X', 'HKDJPY=X', 'CADPLN=X', 'ZARJPY=X', 'GBPDKK=X', 'AUDNOK=X',
    'NOKDKK=X', 'CHFNOK=X', 'GBPMXN=X', 'GBPPLN=X', 'SGDHKD=X', 'AUDCNH=X', 'GBPHKD=X',
    # EUR crosses
    'EURGBP=X', 'EURJPY=X', 'EURCHF=X', 'EURAUD=X', 'EURNZD=X', 'EURCAD=X',
    # GBP crosses
    'GBPJPY=X', 'GBPCHF=X', 'GBPAUD=X', 'GBPCAD=X', 'GBPNZD=X',
    # AUD crosses
    'AUDJPY=X', 'AUDNZD=X', 'AUDCAD=X', 'AUDCHF=X',
    # NZD crosses
    'NZDJPY=X', 'NZDCAD=X', 'NZDCHF=X',
    # CAD crosses
    'CADJPY=X', 'CADCHF=X',
    # CHF crosses
    'CHFJPY=X',
    # Scandinavian
    'EURSEK=X', 'EURNOK=X', 'EURDKK=X', 'USDSEK=X', 'USDNOK=X', 'USDDKK=X',
    'GBPSEK=X', 'GBPNOK=X',
    # Asian
    'EURHKD=X', 'USDSGD=X', 'EURSGD=X', 'SGDJPY=X',
    'USDHKD=X', 'AUDSGD=X', 'CADSGD=X', 'CHFSGD=X', 'NZDSGD=X',
    # EMEA
    'EURPLN=X', 'USDPLN=X', 'EURCZK=X', 'USDCZK=X',
    'EURHUF=X', 'USDHUF=X',
    # LatAm / Other
    'USDMXN=X', 'EURMXN=X', 'USDZAR=X', 'EURZAR=X',
    'USDTRY=X', 'USDBRL=X', 'USDKRW=X', 'USDTHB=X',
    'USDTWD=X', 'USDILS=X', 'USDCLP=X',
    # Global indices
    '^N225', '^GSPC', '^GDAXI', '^FTSE', '^NDX',
]

# ─────────────────────────────────────────────────────────────────────────────
# CRYPTO WATCHLIST
# ─────────────────────────────────────────────────────────────────────────────

CRYPTO_TICKERS: List[str] = [
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'XRP-USD',
    'ADA-USD', 'DOGE-USD', 'AVAX-USD', 'DOT-USD', 'LINK-USD',
]

# ─────────────────────────────────────────────────────────────────────────────
# COMMODITIES WATCHLIST
# ─────────────────────────────────────────────────────────────────────────────

COMMODITY_TICKERS: List[str] = [
    'GC=F',   # Gold
    'CL=F',   # Crude Oil WTI
    'SI=F',   # Silver
    'NG=F',   # Natural Gas
    'HG=F',   # Copper
    'LE=F',   # Live Cattle
    'KC=F',   # Coffee
    'CC=F',   # Cocoa
]

# ─────────────────────────────────────────────────────────────────────────────
# FULL DEFAULT WATCHLIST
# Comment out any group you don't want scanned.
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TICKERS: List[str] = (
    CRYPTO_TICKERS
    + COMMODITY_TICKERS
    + FOREX_TICKERS
    + STOCKS_INDEX
)

# ─────────────────────────────────────────────────────────────────────────────
# CCXT SYMBOL MAPPING (yfinance format → CCXT/Binance format)
# Required for crypto tickers fetched via CCXT.
# ─────────────────────────────────────────────────────────────────────────────

YFINANCE_TO_CCXT: Dict[str, str] = {
    'BTC-USD':  'BTC/USDT',
    'ETH-USD':  'ETH/USDT',
    'SOL-USD':  'SOL/USDT',
    'BNB-USD':  'BNB/USDT',
    'XRP-USD':  'XRP/USDT',
    'ADA-USD':  'ADA/USDT',
    'DOGE-USD': 'DOGE/USDT',
    'AVAX-USD': 'AVAX/USDT',
    'DOT-USD':  'DOT/USDT',
    'MATIC-USD':'MATIC/USDT',
    'LINK-USD': 'LINK/USDT',
    'LTC-USD':  'LTC/USDT',
    'UNI-USD':  'UNI/USDT',
    'ATOM-USD': 'ATOM/USDT',
    'XLM-USD':  'XLM/USDT',
}
