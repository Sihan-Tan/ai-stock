"""验收冒烟：Mock 全链路日终幂等。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BarDaily, TradeCalendar, WatchlistItem
from desk_market.config import load_market_sync_config
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_acceptance_mock_pipeline(_db):
    db = Session(get_engine())
    for d in [date(2024, 7, 1), date(2024, 7, 2), date(2024, 7, 3), date(2024, 7, 4)]:
        db.add(TradeCalendar(cal_date=d, is_open=True))
    db.add(WatchlistItem(symbol="600519.SH", name="茅台"))
    db.flush()
    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date(2024, 7, 4),
        qfq={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1},
        hfq={"open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
    )
    md.seed_minute("600519.SH", "2024-07-04 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    jobs = MarketJobs(db, md=md, akshare=None, config=load_market_sync_config())
    assert jobs.sync_security_list()["status"] == "ok"
    assert jobs.ingest_daily_incremental(asof=date(2024, 7, 4))["status"] in {"ok", "failed"}
    assert (
        db.scalar(select(func.count()).select_from(BarDaily).where(BarDaily.symbol == "600519.SH"))
        >= 1
    )
    n1 = db.scalar(select(func.count()).select_from(BarDaily))
    jobs.ingest_daily_incremental(asof=date(2024, 7, 4))
    n2 = db.scalar(select(func.count()).select_from(BarDaily))
    assert n1 == n2
