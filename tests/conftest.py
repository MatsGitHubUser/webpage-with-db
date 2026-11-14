import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(os.environ.get("APP_DIR", Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(APP_DIR))

import db  # noqa: E402


@pytest.fixture(scope="session")
def table():
    table = db.open_table()
    yield table
    table.close()


@pytest.fixture(autouse=True)
def empty_table(table):
    for entity in table.list_entities(select=["PartitionKey", "RowKey"]):
        table.delete_entity(entity["PartitionKey"], entity["RowKey"])
