from __future__ import annotations

from enum import Enum


class TradingStyle(str, Enum):
    DAY_TRADER = "day_trader"
    SWING_TRADER = "swing_trader"
    SCALPER = "scalper"
    LONG_TERM_INVESTOR = "long_term_investor"


class PrimaryMarket(str, Enum):
    CRYPTOCURRENCY = "cryptocurrency"
    FOREX = "forex"
    STOCKS = "stocks"
    FUTURES = "futures"


TRADING_STYLE_LABELS: dict[TradingStyle, str] = {
    TradingStyle.DAY_TRADER: "Day Trader",
    TradingStyle.SWING_TRADER: "Swing Trader",
    TradingStyle.SCALPER: "Scalper",
    TradingStyle.LONG_TERM_INVESTOR: "Long-term Investor",
}

PRIMARY_MARKET_LABELS: dict[PrimaryMarket, str] = {
    PrimaryMarket.CRYPTOCURRENCY: "Cryptocurrency",
    PrimaryMarket.FOREX: "Forex",
    PrimaryMarket.STOCKS: "Stocks",
    PrimaryMarket.FUTURES: "Futures",
}
