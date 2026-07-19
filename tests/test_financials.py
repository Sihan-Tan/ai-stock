"""财务快照模型测试。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import FinancialSnapshot


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_financial_snapshot_roundtrip(_db):
    db = Session(get_engine())
    row = FinancialSnapshot(
        symbol="600519.SH",
        table_name="Income",
        period="20231231",
        source="qmt",
        payload_json='{"revenue": 1}',
        fetched_at=datetime(2024, 4, 1, 12, 0, 0),
    )
    db.add(row)
    db.flush()
    assert row.id is not None
    db.rollback()
    db.close()
