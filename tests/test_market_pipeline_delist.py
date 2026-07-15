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
from datetime import date

import pandas as pd

from desk_db.models import BarDaily, SecurityMeta
from desk_market import MarketService
from desk_market.daily_ingest import DailyBarIngestor
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


def test_incremental_skips_delisted_and_does_not_update_existing(_db):
    """退市标的不进入增量宇宙；历史日线不被更新。"""
    db = Session(get_engine())
    svc = MarketService(db)
    svc.upsert_daily_bars(
        "999999.SH",
        pd.DataFrame(
            [
                {
                    "date": date(2023, 1, 3),
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                    "amount": 1,
                    "open_hfq": 1,
                    "high_hfq": 1,
                    "low_hfq": 1,
                    "close_hfq": 1,
                    "volume_hfq": 1,
                }
            ]
        ),
    )
    db.commit()
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo("600519.SH", "茅台", "listed"),
            InstrumentInfo("999999.SH", "已退", "delisted"),
        ]
    )
    md.seed_daily(
        "999999.SH",
        date(2024, 1, 2),
        qfq={"open": 9, "high": 9, "low": 9, "close": 9, "volume": 9, "amount": 9},
        hfq={"open": 9, "high": 9, "low": 9, "close": 9, "volume": 9},
    )
    md.seed_daily(
        "600519.SH",
        date(2024, 1, 2),
        qfq={"open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "amount": 1},
        hfq={"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
    )
    SecurityListSync(db, md).run()
    DailyBarIngestor(
        db, md, symbols=None, incremental_days=3, asof=date(2024, 1, 2)
    ).run()
    db.commit()
    rows = db.scalars(select(BarDaily).where(BarDaily.symbol == "999999.SH")).all()
    assert len(rows) == 1 and rows[0].ts == date(2023, 1, 3)
    assert db.scalar(
        select(BarDaily).where(
            BarDaily.symbol == "600519.SH", BarDaily.ts == date(2024, 1, 2)
        )
    )
