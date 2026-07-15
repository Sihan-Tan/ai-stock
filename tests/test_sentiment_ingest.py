"""情绪日终 ingest 幂等。"""

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
from desk_db.models import LimitUpStock
from desk_sentiment import MockQmtSentimentClient, SentimentDailyIngestor, SentimentService


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_sentiment_ingest_snapshot_replace(_db):
    db = Session(get_engine())
    client = MockQmtSentimentClient(
        [
            {
                "symbol": "000001.SZ",
                "name": "A",
                "direct": 1,
                "sealCount": 2,
                "breakUp": 0,
                "upAmount": 1,
            },
            {
                "symbol": "600001.SH",
                "name": "B",
                "direct": 1,
                "sealCount": 1,
                "breakUp": 1,
                "upAmount": 0,
            },
        ]
    )
    asof = date(2024, 7, 4)
    SentimentDailyIngestor(
        db, client, asof=asof, symbols=["000001.SZ", "600001.SH"]
    ).run()
    db.commit()
    snap = SentimentService(db).snapshot(asof)
    assert snap["limit_up_count"] == 2
    assert snap["max_board"] == 2
    n1 = db.scalar(select(func.count()).select_from(LimitUpStock).where(LimitUpStock.asof == asof))
    SentimentDailyIngestor(
        db, client, asof=asof, symbols=["000001.SZ", "600001.SH"]
    ).run()
    db.commit()
    n2 = db.scalar(select(func.count()).select_from(LimitUpStock).where(LimitUpStock.asof == asof))
    assert n1 == n2 == 2
