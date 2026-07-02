from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1 import auth, billing, me, notifications, subscriptions, tickers, trends, webhooks

# Public auth routes return tokens + user (check user.email_verified_at for verification state).
# Protected /api/v1 routes (except /auth/me) require verified email via get_verified_user.
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(webhooks.router)
api_router.include_router(me.router)
api_router.include_router(billing.router)
api_router.include_router(tickers.router)
api_router.include_router(subscriptions.router)
api_router.include_router(notifications.router)
api_router.include_router(trends.router)
