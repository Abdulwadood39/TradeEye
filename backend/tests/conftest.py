import os
import sys
from pathlib import Path

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
