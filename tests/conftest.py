import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(os.environ.get("APP_DIR", Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(APP_DIR))

import db  # noqa: E402


@pytest.fixture(scope="session")
def pool():
    pool = db.open_pool()
    yield pool
    pool.close()


@pytest.fixture(autouse=True)
def empty_table(pool):
    with pool.connection() as conn:
        conn.execute("TRUNCATE comments RESTART IDENTITY")
