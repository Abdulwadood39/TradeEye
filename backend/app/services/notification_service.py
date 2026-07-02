from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.encryption import decrypt_value
from backend.app.db.models.scan import NotificationMessage
from backend.app.db.models.user import UserNotificationSettings
from trend_scanner.alerts.dispatcher import DiscordPlatform, TelegramPlatform

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    channel: str
    external_message_id: str
    success: bool


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_settings(self, user_id: UUID) -> Optional[UserNotificationSettings]:
        result = await self.db.execute(
            select(UserNotificationSettings).where(UserNotificationSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def delete_previous(
        self,
        user_id: UUID,
        ticker_id: UUID,
        timeframe_id: UUID,
        settings: UserNotificationSettings,
    ) -> None:
        result = await self.db.execute(
            select(NotificationMessage).where(
                NotificationMessage.user_id == user_id,
                NotificationMessage.ticker_id == ticker_id,
                NotificationMessage.timeframe_id == timeframe_id,
            )
        )
        messages = list(result.scalars().all())
        discord_url = decrypt_value(settings.discord_webhook_url_enc)
        telegram_token = decrypt_value(settings.telegram_bot_token_enc)
        telegram_chat = settings.telegram_chat_id

        for msg in messages:
            try:
                if msg.channel == "discord" and discord_url:
                    DiscordPlatform(discord_url).delete_message(msg.external_message_id)
                elif msg.channel == "telegram" and telegram_token and telegram_chat:
                    TelegramPlatform(telegram_token, telegram_chat).delete_message(
                        telegram_chat, msg.external_message_id
                    )
            except Exception as exc:
                logger.warning("Failed to delete message %s: %s", msg.id, exc)
            await self.db.delete(msg)

    async def send_trend_alert(
        self,
        *,
        user_id: UUID,
        display_name: str,
        yfinance_symbol: str,
        timeframe: str,
        direction: str,
        score: int,
        confidence: float,
        bars_scanned: int,
        chart_path: Optional[str],
        ticker_id: UUID,
        timeframe_id: UUID,
        trend_event_id: UUID,
    ) -> list[SendResult]:
        settings = await self._get_settings(user_id)
        if settings is None:
            return []

        if settings.delete_previous_messages:
            await self.delete_previous(user_id, ticker_id, timeframe_id, settings)

        from trend_scanner.engine.trend_engine import TrendResult

        result = TrendResult(
            ticker=display_name,
            timeframe=timeframe,
            direction=direction.lower(),
            score=score,
            confidence=confidence,
            candles_analyzed=bars_scanned,
            chart_path=chart_path,
        )

        channels = []
        if settings.preferred_channel in ("discord", "both"):
            channels.append("discord")
        if settings.preferred_channel in ("telegram", "both"):
            channels.append("telegram")

        sent: list[SendResult] = []
        for channel in channels:
            if channel == "discord":
                webhook = decrypt_value(settings.discord_webhook_url_enc)
                if not webhook:
                    if settings.discord_webhook_url_enc:
                        logger.warning("Discord webhook configured for user %s but could not be decrypted", user_id)
                    continue
                platform = DiscordPlatform(webhook)
                success, msg_id = platform.send_alert_with_id(result)
                if msg_id:
                    self.db.add(
                        NotificationMessage(
                            user_id=user_id,
                            ticker_id=ticker_id,
                            timeframe_id=timeframe_id,
                            bars_scanned=bars_scanned,
                            channel="discord",
                            external_message_id=msg_id,
                            trend_event_id=trend_event_id,
                            sent_at=datetime.now(timezone.utc),
                        )
                    )
                sent.append(SendResult(channel="discord", external_message_id=msg_id or "", success=success))

            elif channel == "telegram":
                token = decrypt_value(settings.telegram_bot_token_enc)
                chat_id = settings.telegram_chat_id
                if not token or not chat_id:
                    continue
                platform = TelegramPlatform(token, chat_id)
                success, msg_id = platform.send_alert_with_id(result)
                if msg_id:
                    self.db.add(
                        NotificationMessage(
                            user_id=user_id,
                            ticker_id=ticker_id,
                            timeframe_id=timeframe_id,
                            bars_scanned=bars_scanned,
                            channel="telegram",
                            external_message_id=msg_id,
                            trend_event_id=trend_event_id,
                            sent_at=datetime.now(timezone.utc),
                        )
                    )
                sent.append(SendResult(channel="telegram", external_message_id=msg_id or "", success=success))

        return sent
