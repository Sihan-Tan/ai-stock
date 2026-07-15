"""情绪/龙虎榜验收冒烟。"""

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
from desk_db.models import TradeCalendar
from desk_lhb import FakeLhbClient, LhbService
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_sentiment import MockQmtSentimentClient, SentimentService


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_acceptance_sentiment_lhb(_db):
    db = Session(get_engine())
    asof = date(2024, 7, 4)
    db.add(TradeCalendar(cal_date=asof, is_open=True))
    db.flush()
    sent = MockQmtSentimentClient(
        [
            {
                "symbol": "000001.SZ",
                "name": "A",
                "direct": 1,
                "sealCount": 3,
                "breakUp": 0,
                "upAmount": 1,
            }
        ]
    )
    lhb = FakeLhbClient(
        [
            {
                "symbol": "300750.SZ",
                "name": "宁德",
                "reason": "振幅",
                "net_buy": 1.0,
                "seats": [{"side": "buy", "seat_name": "机构专用", "amount": 9}],
            }
        ]
    )
    jobs = MarketJobs(
        db,
        md=MockQmtMarketData(
            instruments=[InstrumentInfo("000001.SZ", status="listed")]
        ),
        sentiment_client=sent,
        lhb_client=lhb,
    )
    assert jobs.sync_sentiment_daily(asof=asof)["status"] == "ok"
    assert jobs.sync_lhb_daily(asof=asof)["status"] == "ok"
    snap = SentimentService(db).snapshot(asof)
    assert snap["max_board"] == 3
    assert LhbService(db).by_date(asof)[0]["seats"][0]["is_institution"] is True
