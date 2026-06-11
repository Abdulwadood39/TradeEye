from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_verified_user
from backend.app.core.encryption import decrypt_value, encrypt_value
from backend.app.db.models.user import User, UserNotificationSettings
from backend.app.db.session import get_db
from backend.app.schemas.catalog import NotificationSettingsResponse, NotificationSettingsUpdate

router = APIRouter(prefix="/me/notifications", tags=["notifications"])


@router.get("", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationSettingsResponse:
    result = await db.execute(
        select(UserNotificationSettings).where(UserNotificationSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        return NotificationSettingsResponse(
            preferred_channel="discord",
            delete_previous_messages=False,
            notify_on="trend_only",
            has_discord=False,
            has_telegram=False,
        )
    return NotificationSettingsResponse(
        preferred_channel=settings.preferred_channel,
        delete_previous_messages=settings.delete_previous_messages,
        notify_on=settings.notify_on,
        has_discord=bool(settings.discord_webhook_url_enc),
        has_telegram=bool(settings.telegram_bot_token_enc and settings.telegram_chat_id),
    )


@router.put("", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    body: NotificationSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationSettingsResponse:
    result = await db.execute(
        select(UserNotificationSettings).where(UserNotificationSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = UserNotificationSettings(user_id=user.id)
        db.add(settings)

    if body.discord_webhook_url is not None:
        settings.discord_webhook_url_enc = encrypt_value(body.discord_webhook_url or None)
    if body.telegram_bot_token is not None:
        settings.telegram_bot_token_enc = encrypt_value(body.telegram_bot_token or None)
    if body.telegram_chat_id is not None:
        settings.telegram_chat_id = body.telegram_chat_id or None
    if body.preferred_channel is not None:
        settings.preferred_channel = body.preferred_channel
    if body.delete_previous_messages is not None:
        settings.delete_previous_messages = body.delete_previous_messages

    await db.flush()
    return NotificationSettingsResponse(
        preferred_channel=settings.preferred_channel,
        delete_previous_messages=settings.delete_previous_messages,
        notify_on=settings.notify_on,
        has_discord=bool(settings.discord_webhook_url_enc),
        has_telegram=bool(settings.telegram_bot_token_enc and settings.telegram_chat_id),
    )
