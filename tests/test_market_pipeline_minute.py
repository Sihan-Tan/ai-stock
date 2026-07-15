"""分钟宇宙与 3 交易日 purge。"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BarMinute, TradeCalendar, WatchlistItem
from desk_market import MarketService
from desk_market.minute_ingest import MinuteBarIngestor, compute_minute_purge_cutoff
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_market.security_universe import SecurityListSync


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def _seed_calendar(db, days: list[tuple[date, bool]]):
    for d, open_ in days:
        db.add(TradeCalendar(cal_date=d, is_open=open_))
    db.flush()


def test_purge_keeps_only_last_3_trade_days(_db):
    db = Session(get_engine())
    _seed_calendar(
        db,
        [
            (date(2024, 1, 2), True),
            (date(2024, 1, 3), True),
            (date(2024, 1, 4), True),
            (date(2024, 1, 5), True),
            (date(2024, 1, 8), True),
        ],
    )
    svc = MarketService(db)
    for d in [2, 3, 4, 5, 8]:
        svc.upsert_minute_bars(
            "600519.SH",
            pd.DataFrame(
                [
                    {
                        "ts": datetime(2024, 1, d, 10, 0, 0),
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 1,
                        "amount": 1,
                    }
                ]
            ),
        )
    db.commit()
    cutoff = compute_minute_purge_cutoff(db, asof=date(2024, 1, 8))
    assert cutoff == datetime(2024, 1, 3, 9, 30, 0)
    deleted = svc.purge_minute_before(cutoff)
    assert deleted >= 1
    left = db.scalars(select(BarMinute)).all()
    assert all(r.ts >= cutoff for r in left)
    assert {r.ts.day for r in left} <= {3, 4, 5, 8}


def test_minute_universe_watchlist_union_indices_skips_delisted(_db):
    db = Session(get_engine())
    db.add(WatchlistItem(symbol="600519.SH", name="茅台"))
    db.add(WatchlistItem(symbol="999999.SH", name="退市自选"))
    db.flush()
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo("600519.SH", status="listed"),
            InstrumentInfo("999999.SH", status="delisted"),
            InstrumentInfo("000300.SH", status="listed"),
        ]
    )
    SecurityListSync(db, md).run()
    md.seed_minute("600519.SH", "2024-01-08 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    md.seed_minute("000300.SH", "2024-01-08 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    md.seed_minute("999999.SH", "2024-01-08 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    MinuteBarIngestor(db, md, index_symbols=["000300.SH"], asof=date(2024, 1, 8), purge=False).run()
    db.commit()
    syms = {r.symbol for r in db.scalars(select(BarMinute)).all()}
    assert "600519.SH" in syms and "000300.SH" in syms
    assert "999999.SH" not in syms
