from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → project root is three levels up
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"


def _resolved_env_file() -> str | None:
    if _ENV_FILE.is_file():
        return str(_ENV_FILE)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolved_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TradeEye API"
    debug: bool = False
    seed_dev_user: bool = False

    database_url: str = "mysql+aiomysql://tradeeye:tradeeye@localhost:3306/tradeeye?charset=utf8mb4"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    encryption_key: str = ""  # Fernet key; generate if empty at startup warning

    frontend_url: str = "http://localhost:3000"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@tradeeye.app"
    smtp_use_tls: bool = True

    email_verification_expire_hours: int = 24
    password_reset_expire_hours: int = 1

    admin_username: str = "admin"
    admin_password_hash: str = ""  # bcrypt hash
    session_secret_key: str = "change-me-session-secret"

    cors_origins: str = "http://localhost:3000"

    chart_tmp_dir: str = "/tmp/tradeeye/charts"
    default_subscription_bars: int = 2500
    scan_workers: int = 16
    vetoes_enabled: bool = True

    @property
    def cors_origins_list(self) -> List[str]:
        origins: list[str] = []
        for origin in self.cors_origins.split(","):
            origin = origin.strip().rstrip("/")
            if origin:
                origins.append(origin)
        return origins

    @model_validator(mode="after")
    def unescape_bcrypt_hash(self) -> "Settings":
        # Docker Compose .env uses $$ to escape bcrypt $ chars
        if self.admin_password_hash and "$$" in self.admin_password_hash:
            self.admin_password_hash = self.admin_password_hash.replace("$$", "$")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
