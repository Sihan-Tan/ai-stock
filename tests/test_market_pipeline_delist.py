"""退市不进入在市宇宙；已有退市日线不再被增量更新。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import SecurityMeta
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_market.security_universe import SecurityListSync


@pytest.fixture()
def _db():
    """SQLite 内存库 + create_all（与 test_market_pipeline_models 一致）。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    reset_engine()
    get_settings.cache_clear()


def test_security_list_sync_marks_and_filters(_db):
    db = Session(get_engine())
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo("600519.SH", "茅台", "listed"),
            InstrumentInfo("999999.SH", "已退", "delisted"),
        ]
    )
    sync = SecurityListSync(db, md)
    universe = sync.run()
    assert universe == ["600519.SH"]
    meta = {m.symbol: m for m in db.scalars(select(SecurityMeta)).all()}
    assert meta["999999.SH"].is_delisted is True
    assert meta["600519.SH"].is_delisted is False
    db.commit()
