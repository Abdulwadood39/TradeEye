from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1 import auth, me, notifications, subscriptions, tickers, trends

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(tickers.router)
api_router.include_router(subscriptions.router)
api_router.include_router(notifications.router)
api_router.include_router(trends.router)
