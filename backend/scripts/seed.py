#!/usr/bin/env python3
"""Seed database with tickers, timeframes, indicators, plans, and scan schedules."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.security import hash_password
from backend.app.db.models.billing import Plan, Subscription
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe, TimeframeScanSchedule
from backend.app.db.models.user import User
from backend.app.db.session import async_session_factory, engine
from backend.app.db.base import Base
from trend_scanner.config.tickers import (
    COMMODITY_TICKERS,
    CRYPTO_TICKERS,
    FOREX_TICKERS,
    STOCKS_INDEX,
)

COMMODITY_ALIASES = {
    "GC=F": "Gold",
    "CL=F": "Crude Oil WTI",
    "SI=F": "Silver",
    "NG=F": "Natural Gas",
    "HG=F": "Copper",
    "LE=F": "Live Cattle",
    "KC=F": "Coffee",
    "CC=F": "Cocoa",
}

CRYPTO_ALIASES = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "BNB-USD": "BNB",
    "XRP-USD": "XRP",
    "ADA-USD": "Cardano",
    "DOGE-USD": "Dogecoin",
    "AVAX-USD": "Avalanche",
    "DOT-USD": "Polkadot",
    "LINK-USD": "Chainlink",
}


def _forex_alias(symbol: str) -> str:
    base = symbol.replace("=X", "")
    if len(base) == 6:
        return f"{base[:3]}/{base[3:]}"
    return base


def _stock_alias(symbol: str) -> str:
    return symbol


TIMEFRAMES = [
    ("1m", "1 Minute", 180),
    ("3m", "3 Minutes", 180),
    ("5m", "5 Minutes", 180),
    ("15m", "15 Minutes", 15),
    ("30m", "30 Minutes", 30),
    ("1h", "1 Hour", 1440),
    ("1d", "1 Day", 1440),
    ("1w", "1 Week", 10080),
]

DEV_USER_EMAIL = "admin@tradepulse.com"
DEV_USER_PASSWORD = "admin123"


def _should_seed_dev_user() -> bool:
    settings = get_settings()
    env = os.getenv("SEED_DEV_USER")
    if env is not None:
        return env.lower() in ("1", "true", "yes")
    return settings.seed_dev_user or settings.debug


async def _seed_dev_user(db) -> None:
    existing = (
        await db.execute(select(User).where(User.email == DEV_USER_EMAIL))
    ).scalar_one_or_none()

    if existing is None:
        user = User(
            email=DEV_USER_EMAIL,
            password_hash=hash_password(DEV_USER_PASSWORD),
            full_name="TradePulse Admin",
            trading_style="swing_trader",
            primary_market="forex",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        # print(f"  Created dev user: {DEV_USER_EMAIL} / {DEV_USER_PASSWORD}")
    else:
        user = existing
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        print(f"  Dev user already exists: {DEV_USER_EMAIL}")

    plan = (await db.execute(select(Plan).where(Plan.slug == "free"))).scalar_one_or_none()
    if plan:
        billing_sub = (
            await db.execute(select(Subscription).where(Subscription.user_id == user.id))
        ).scalar_one_or_none()
        if billing_sub is None:
            db.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        if (await db.execute(select(Plan).where(Plan.slug == "free"))).scalar_one_or_none() is None:
            db.add(
                Plan(
                    slug="free",
                    name="Free Plan",
                    max_subscriptions=20,
                    max_timeframes=8,
                    price_cents=0,
                    currency="USD",
                    billing_interval="month",
                )
            )

        if (await db.execute(select(IndicatorType).where(IndicatorType.slug == "continuous_trend"))).scalar_one_or_none() is None:
            db.add(
                IndicatorType(
                    slug="continuous_trend",
                    name="Continuous Trend",
                    description="Identifies sustained up/down trends using 5 statistical signals",
                )
            )

        for code, label, interval in TIMEFRAMES:
            existing = (await db.execute(select(Timeframe).where(Timeframe.code == code))).scalar_one_or_none()
            if existing is None:
                tf = Timeframe(code=code, label=label)
                db.add(tf)
                await db.flush()
                db.add(TimeframeScanSchedule(timeframe_id=tf.id, interval_minutes=interval, is_enabled=code in ("1m", "1h")))
            else:
                sched = (
                    await db.execute(
                        select(TimeframeScanSchedule).where(TimeframeScanSchedule.timeframe_id == existing.id)
                    )
                ).scalar_one_or_none()
                if sched is None:
                    db.add(
                        TimeframeScanSchedule(
                            timeframe_id=existing.id,
                            interval_minutes=interval,
                            is_enabled=code in ("1m", "1h"),
                        )
                    )

        async def upsert_ticker(symbol: str, display_name: str, category: str) -> None:
            existing = (await db.execute(select(Ticker).where(Ticker.yfinance_symbol == symbol))).scalar_one_or_none()
            if existing is None:
                db.add(Ticker(yfinance_symbol=symbol, display_name=display_name, category=category))

        for symbol in COMMODITY_TICKERS:
            await upsert_ticker(symbol, COMMODITY_ALIASES.get(symbol, symbol), "commodity")
        for symbol in CRYPTO_TICKERS:
            await upsert_ticker(symbol, CRYPTO_ALIASES.get(symbol, symbol), "crypto")
        for symbol in FOREX_TICKERS:
            await upsert_ticker(symbol, _forex_alias(symbol), "forex")
        for symbol in STOCKS_INDEX:
            await upsert_ticker(symbol, _stock_alias(symbol), "stock")

        if _should_seed_dev_user():
            print("==> Seeding development user")
            await _seed_dev_user(db)
        else:
            print("==> Skipping dev user (set SEED_DEV_USER=true or DEBUG=true to enable)")

        await db.commit()
        print("Seed completed successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
