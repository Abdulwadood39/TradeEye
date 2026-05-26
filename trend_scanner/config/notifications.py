"""
config/notifications.py — Alert channel configuration.

Webhook URLs and bot tokens are loaded from .env — never hardcode them here.
Toggle each channel on/off with the `enabled` flag.

Channel routing:
  discord          → confirmed trends (scored + passed all veto gates)
  discord_vetos    → vetoed results (would have fired but a gate blocked it)
  discord_no_trend → tickers that scored below min_signals_for_trend
  telegram         → confirmed trends (same as discord channel)
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TelegramConfig:
    # Toggle Telegram alerts for confirmed trends
    enabled: bool = False
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))


@dataclass
class DiscordConfig:
    """Trend alerts channel — fires for confirmed trends only."""
    enabled: bool = False
    webhook_url: str = field(default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL", ""))


@dataclass
class DiscordVetosConfig:
    """
    Vetos channel — fires when signals pass scoring but are killed by a veto gate.
    Good for monitoring what would have fired without filtering.
    Falls back to DISCORD_ALL_WEBHOOK_URL if the new key isn't set (backward compat).
    """
    enabled: bool = False
    webhook_url: str = field(
        default_factory=lambda: os.getenv(
            "DISCORD_VETOS_WEBHOOK_URL",
            os.getenv("DISCORD_ALL_WEBHOOK_URL", ""),
        )
    )


@dataclass
class DiscordNoTrendConfig:
    """
    No-trend channel — one consolidated message per scan listing all tickers
    that never reached the signal threshold.
    High-volume channel, sent as a single batched message to avoid rate-limiting.
    """
    enabled: bool = True
    webhook_url: str = field(default_factory=lambda: os.getenv("DISCORD_NO_TREND_WEBHOOK_URL", ""))


@dataclass
class NotificationsConfig:
    telegram:         TelegramConfig       = field(default_factory=TelegramConfig)
    discord:          DiscordConfig        = field(default_factory=DiscordConfig)
    discord_vetos:    DiscordVetosConfig   = field(default_factory=DiscordVetosConfig)
    discord_no_trend: DiscordNoTrendConfig = field(default_factory=DiscordNoTrendConfig)
