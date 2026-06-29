from __future__ import annotations

import logging

from backend.app.core.config import get_settings

# Third-party loggers that must stay quiet during scans (CCXT dumps full OHLCV JSON at DEBUG).
_QUIET_LOGGERS = (
    "sqlalchemy.engine",
    "sqlalchemy.engine.Engine",
    "sqlalchemy.pool",
    "sqlalchemy.orm",
    "yfinance",
    "peewee",
    "ccxt",
    "ccxt.base",
    "ccxt.base.exchange",
    "urllib3",
    "urllib3.connectionpool",
    "requests",
    "httpx",
    "httpcore",
    "aiomysql",
    "asyncio",
    "watchfiles",
    "watchfiles.main",
    "apscheduler",
    "apscheduler.scheduler",
    "apscheduler.executors.default",
    "trend_scanner.data.fetcher",
    "trend_scanner.alerts.dispatcher",
    "trend_scanner.alerts.notifier",
    "matplotlib",
    "PIL",
)


def configure_logging() -> None:
    settings = get_settings()
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    if settings.http_access_log:
        logging.getLogger("uvicorn.access").setLevel(level)
        logging.getLogger("uvicorn.error").setLevel(level)
    else:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    if settings.scan_verbose:
        logging.getLogger("trend_scanner.data.fetcher").setLevel(logging.INFO)
        logging.getLogger("trend_scanner.alerts.dispatcher").setLevel(logging.INFO)

    if settings.sql_echo:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
