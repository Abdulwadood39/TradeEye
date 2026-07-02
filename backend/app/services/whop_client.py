from __future__ import annotations

from functools import lru_cache

from whop_sdk import Whop

from backend.app.core.config import get_settings


@lru_cache
def get_whop_client() -> Whop | None:
    settings = get_settings()
    if not settings.whop_api_key:
        return None
    return Whop(
        api_key=settings.whop_api_key,
        webhook_key=settings.whop_webhook_secret or None,
    )
