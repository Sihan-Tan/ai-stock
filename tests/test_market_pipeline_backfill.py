"""日终增量只请求近 N 日。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_market.daily_ingest import DailyBarIngestor
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_market.security_universe import SecurityListSync


@pytest.fixture()
def _db():
    """SQLite 内存库 + create_all。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    reset_engine()
    get_settings.cache_clear()


class RecordingMd(MockQmtMarketData):
    """记录 get_daily_bars 调用窗口。"""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        return super().get_daily_bars(symbol, start, end)


def test_incremental_requests_only_near_window(_db):
    db = Session(get_engine())
    md = RecordingMd(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date(2024, 6, 3),
        qfq={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1},
        hfq={"open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
    )
    SecurityListSync(db, md).run()
    DailyBarIngestor(
        db,
        md,
        symbols=None,
        incremental_days=2,
        asof=date(2024, 6, 3),
        daily_start_date=date(2018, 1, 1),
    ).run()
    assert md.calls
    for _, start, end in md.calls:
        assert start >= date(2024, 6, 2)
        assert end <= date(2024, 6, 3)
        assert start >= date(2018, 1, 1)
