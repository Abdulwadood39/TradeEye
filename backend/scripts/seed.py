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
from backend.app.core.encryption import encrypt_value
from backend.app.core.security import hash_password
from backend.app.db.models.billing import Plan, Subscription
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe, TimeframeScanSchedule
from backend.app.db.models.user import User, UserNotificationSettings, UserSubscription
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
ADMIN_PLAN_SLUG = "admin"
PRO_PLAN_SLUG = "pro"
ADDON_PLAN_SLUG = "addon-subs-50"
PRO_WHOP_PLAN_ID = "plan_ZUwmW7PbwcLEF"
ADMIN_TIMEFRAME_CODES = ("1m", "1h")


def _admin_discord_webhook_url() -> str | None:
    return os.getenv("SEED_ADMIN_DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")


async def _ensure_pro_plan(db) -> Plan:
    plan = (await db.execute(select(Plan).where(Plan.slug == PRO_PLAN_SLUG))).scalar_one_or_none()
    if plan is None:
        plan = Plan(
            slug=PRO_PLAN_SLUG,
            name="Pro",
            max_subscriptions=100,
            max_timeframes=8,
            price_cents=999,
            currency="USD",
            billing_interval="month",
            whop_plan_id=PRO_WHOP_PLAN_ID,
            plan_kind="subscription",
        )
        db.add(plan)
        await db.flush()
    else:
        plan.name = "Pro"
        plan.max_subscriptions = 100
        plan.max_timeframes = 8
        plan.price_cents = 999
        plan.whop_plan_id = PRO_WHOP_PLAN_ID
        plan.plan_kind = "subscription"
        plan.is_active = True
    return plan


async def _ensure_addon_plan(db) -> Plan | None:
    settings = get_settings()
    whop_plan_id = settings.whop_addon_plan_id.strip()
    if not whop_plan_id:
        return None

    plan = (await db.execute(select(Plan).where(Plan.slug == ADDON_PLAN_SLUG))).scalar_one_or_none()
    if plan is None:
        plan = Plan(
            slug=ADDON_PLAN_SLUG,
            name="+50 Subscriptions",
            max_subscriptions=0,
            max_timeframes=0,
            price_cents=500,
            currency="USD",
            billing_interval="month",
            whop_plan_id=whop_plan_id,
            plan_kind="addon",
            addon_bonus_subscriptions=50,
        )
        db.add(plan)
        await db.flush()
    else:
        plan.name = "+50 Subscriptions"
        plan.price_cents = 500
        plan.whop_plan_id = whop_plan_id
        plan.plan_kind = "addon"
        plan.addon_bonus_subscriptions = 50
        plan.is_active = True
    return plan


async def _ensure_admin_plan(db) -> Plan:
    plan = (await db.execute(select(Plan).where(Plan.slug == ADMIN_PLAN_SLUG))).scalar_one_or_none()
    if plan is None:
        plan = Plan(
            slug=ADMIN_PLAN_SLUG,
            name="Admin Plan",
            max_subscriptions=1000,
            max_timeframes=8,
            price_cents=0,
            currency="USD",
            billing_interval="month",
            plan_kind="internal",
        )
        db.add(plan)
        await db.flush()
    return plan


async def _seed_admin_subscriptions(db, user: User) -> None:
    indicator = (
        await db.execute(select(IndicatorType).where(IndicatorType.slug == "continuous_trend"))
    ).scalar_one()
    timeframes = list(
        (
            await db.execute(
                select(Timeframe).where(Timeframe.code.in_(ADMIN_TIMEFRAME_CODES), Timeframe.is_active.is_(True))
            )
        ).scalars()
    )
    tickers = list((await db.execute(select(Ticker).where(Ticker.is_active.is_(True)))).scalars())
    if not timeframes or not tickers:
        print("  Skipping admin subscriptions (no tickers or timeframes)")
        return

    existing = set(
        (
            await db.execute(
                select(
                    UserSubscription.ticker_id,
                    UserSubscription.timeframe_id,
                ).where(UserSubscription.user_id == user.id)
            )
        ).all()
    )

    bars = get_settings().default_subscription_bars
    created = 0
    batch: list[UserSubscription] = []
    for timeframe in timeframes:
        for ticker in tickers:
            key = (ticker.id, timeframe.id)
            if key in existing:
                continue
            batch.append(
                UserSubscription(
                    user_id=user.id,
                    ticker_id=ticker.id,
                    timeframe_id=timeframe.id,
                    indicator_type_id=indicator.id,
                    bars=bars,
                )
            )
            created += 1
            if len(batch) >= 100:
                db.add_all(batch)
                await db.flush()
                batch.clear()

    if batch:
        db.add_all(batch)
        await db.flush()

    print(f"  Admin subscriptions: {created} created ({len(tickers)} tickers x {len(timeframes)} timeframes)")


async def _seed_admin_notifications(db, user: User) -> None:
    webhook_url = _admin_discord_webhook_url()
    if not webhook_url:
        print("  Skipping admin Discord webhook (set DISCORD_WEBHOOK_URL or SEED_ADMIN_DISCORD_WEBHOOK_URL)")
        return

    settings = (
        await db.execute(select(UserNotificationSettings).where(UserNotificationSettings.user_id == user.id))
    ).scalar_one_or_none()
    if settings is None:
        settings = UserNotificationSettings(user_id=user.id)
        db.add(settings)

    settings.discord_webhook_url_enc = encrypt_value(webhook_url)
    settings.preferred_channel = "discord"
    settings.delete_previous_messages = False
    print("  Admin Discord notifications configured")


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

    plan = await _ensure_admin_plan(db)
    billing_sub = (
        await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    ).scalar_one_or_none()
    if billing_sub is None:
        db.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    else:
        billing_sub.plan_id = plan.id

    await _seed_admin_subscriptions(db, user)
    await _seed_admin_notifications(db, user)


async def seed() -> None:
    print("==> Creating tables (if missing)")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("==> Tables ready")

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
                    plan_kind="internal",
                )
            )

        await _ensure_pro_plan(db)
        addon = await _ensure_addon_plan(db)
        if addon is not None:
            print(f"  Addon plan linked to Whop: {addon.whop_plan_id}")

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

        async def upsert_tickers(entries: list[tuple[str, str, str]]) -> None:
            symbols = [symbol for symbol, _, _ in entries]
            existing_symbols = set(
                (
                    await db.execute(select(Ticker.yfinance_symbol).where(Ticker.yfinance_symbol.in_(symbols)))
                ).scalars()
            )
            added = 0
            for symbol, display_name, category in entries:
                if symbol in existing_symbols:
                    continue
                db.add(Ticker(yfinance_symbol=symbol, display_name=display_name, category=category))
                added += 1
            if added:
                print(f"  Added {added} tickers")

        ticker_entries: list[tuple[str, str, str]] = []
        for symbol in COMMODITY_TICKERS:
            ticker_entries.append((symbol, COMMODITY_ALIASES.get(symbol, symbol), "commodity"))
        for symbol in CRYPTO_TICKERS:
            ticker_entries.append((symbol, CRYPTO_ALIASES.get(symbol, symbol), "crypto"))
        for symbol in FOREX_TICKERS:
            ticker_entries.append((symbol, _forex_alias(symbol), "forex"))
        for symbol in STOCKS_INDEX:
            ticker_entries.append((symbol, _stock_alias(symbol), "stock"))

        print(f"==> Seeding {len(ticker_entries)} tickers")
        await upsert_tickers(ticker_entries)

        if _should_seed_dev_user():
            print("==> Seeding development user")
            await _seed_dev_user(db)
        else:
            print("==> Skipping dev user (set SEED_DEV_USER=true or DEBUG=true to enable)")

        await db.commit()
        print("Seed completed successfully.")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
