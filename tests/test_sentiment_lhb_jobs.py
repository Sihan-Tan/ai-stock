"""情绪/龙虎榜 Job 可观测性。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import MarketJobRun, TradeCalendar
from desk_lhb import FakeLhbClient
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_sentiment import MockQmtSentimentClient


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


class DeadSentiment(MockQmtSentimentClient):
    def fetch_limit_performance(self, symbols, asof):
        raise RuntimeError("xtdata limitupperformance unavailable")


def test_sync_sentiment_records_failure(_db):
    db = Session(get_engine())
    asof = date(2024, 7, 4)
    db.add(TradeCalendar(cal_date=asof, is_open=True))
    db.flush()
    jobs = MarketJobs(
        db,
        md=MockQmtMarketData(
            instruments=[InstrumentInfo("000001.SZ", status="listed")]
        ),
        sentiment_client=DeadSentiment(),
    )
    out = jobs.sync_sentiment_daily(asof=asof)
    assert out["status"] == "failed"
    row = db.scalars(
        select(MarketJobRun).where(MarketJobRun.job_id == "sync_sentiment_daily")
    ).first()
    assert row is not None and row.status == "failed"


def test_sync_lhb_ok_with_fake(_db):
    db = Session(get_engine())
    asof = date(2024, 7, 4)
    db.add(TradeCalendar(cal_date=asof, is_open=True))
    db.flush()
    jobs = MarketJobs(
        db,
        md=MockQmtMarketData(instruments=[]),
        lhb_client=FakeLhbClient(
            [
                {
                    "symbol": "300750.SZ",
                    "name": "宁德",
                    "reason": "振幅",
                    "net_buy": 1.0,
                    "seats": [],
                }
            ]
        ),
    )
    out = jobs.sync_lhb_daily(asof=asof)
    assert out["status"] == "ok"
    assert out["symbols_done"] == 1
