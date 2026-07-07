from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from backend.app.admin.routes import router as admin_router
from backend.app.api.v1.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging_config import configure_logging
from backend.app.core.limiter import limiter
from backend.app.db.session import engine
from backend.app.indicators.registry import init_registry
from backend.app.services.scan_scheduler import load_schedules, shutdown_scheduler, start_scheduler

logger = logging.getLogger(__name__)


def _sweep_orphan_charts(chart_dir: str, max_age_seconds: int = 3600) -> None:
    if not os.path.isdir(chart_dir):
        return
    now = time.time()
    for root, _, files in os.walk(chart_dir):
        for fname in files:
            path = os.path.join(root, fname)
            try:
                if now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
            except OSError:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    os.makedirs(settings.chart_tmp_dir, exist_ok=True)
    _sweep_orphan_charts(settings.chart_tmp_dir)
    init_registry()
    start_scheduler()
    await load_schedules()
    logger.info("TradeEye API started")
    yield
    shutdown_scheduler()
    await engine.dispose()
    logger.info("TradeEye API stopped")


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)

    app.include_router(api_router)
    app.include_router(admin_router)

    @app.get("/")
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        return {"status": "ready", "scheduler": "running"}

    return app


app = create_app()
