import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "mysql+aiomysql://tradeeye:tradeeye@localhost:3306/tradeeye?charset=utf8mb4")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret")
os.environ.setdefault("CHART_TMP_DIR", "/tmp/tradeeye_test_charts")


@pytest.fixture
def chart_tmp_dir(tmp_path):
    path = tmp_path / "charts"
    path.mkdir()
    return str(path)


@pytest.fixture
def test_user():
    return SimpleNamespace(
        id=uuid4(),
        email="billing-test@example.com",
        full_name="Billing Test",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def db_session():
    pytest.importorskip("aiosqlite")
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
