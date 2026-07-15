"""日终增量只请求近 N 日。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BarDaily
from desk_market.daily_ingest import DailyBarIngestor
from desk_market.history_backfill import HistoryBackfill
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


class FailThenEmptyMd(MockQmtMarketData):
    """QMT 返回空，迫使走 AkShare。"""

    def get_daily_bars(self, symbol, start, end):
        return pd.DataFrame()


class FakeAk:
    """测试用 AkShare 替身。"""

    def __init__(self):
        self.calls = []

    def get_daily_bars(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        return pd.DataFrame(
            [
                {
                    "date": date(2019, 1, 2),
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                    "amount": 1,
                    "open_hfq": 10,
                    "high_hfq": 10,
                    "low_hfq": 10,
                    "close_hfq": 10,
                    "volume_hfq": 1,
                }
            ]
        )


def test_backfill_clamps_to_daily_start_and_does_not_request_before(_db):
    db = Session(get_engine())
    md = FailThenEmptyMd(instruments=[InstrumentInfo("600519.SH", status="listed")])
    ak = FakeAk()
    HistoryBackfill(
        db,
        md,
        akshare=ak,
        daily_start_date=date(2018, 1, 1),
        symbols=["600519.SH"],
        forced_gap=(date(2017, 1, 1), date(2019, 1, 5)),
    ).run()
    assert ak.calls
    _, start, end = ak.calls[0]
    assert start == date(2018, 1, 1)
    assert start >= date(2018, 1, 1)


def test_backfill_prefers_qmt_then_akshare(_db):
    db = Session(get_engine())
    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date(2019, 6, 3),
        qfq={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1},
        hfq={"open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
    )
    ak = FakeAk()
    HistoryBackfill(
        db,
        md,
        akshare=ak,
        daily_start_date=date(2018, 1, 1),
        symbols=["600519.SH"],
        forced_gap=(date(2019, 6, 3), date(2019, 6, 3)),
    ).run()
    assert not ak.calls
    row = db.scalar(select(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert row is not None and float(row.close_hfq) == 2.0
