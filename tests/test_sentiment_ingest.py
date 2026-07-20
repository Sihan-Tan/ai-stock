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


def test_sentiment_snapshot_falls_back_to_latest_asof(_db, monkeypatch):
    """未指定 asof 且今日无有效涨停时，回退到库内最近有统计的交易日。"""
    from desk_db.models import LimitUpStat, LimitUpStock

    monkeypatch.setattr("desk_sentiment.beijing_today", lambda: date(2026, 7, 20))

    db = Session(get_engine())
    try:
        hist = date(2026, 7, 14)
        db.add(
            LimitUpStat(
                asof=hist,
                limit_up_count=68,
                limit_down_count=12,
                max_board=7,
                promote_rate=0.42,
                break_rate=0.18,
            )
        )
        db.add(
            LimitUpStock(
                asof=hist,
                symbol="000001.SZ",
                name="示例",
                board_height=7,
                seal_amount=1.0,
                concept="",
                status="sealed",
            )
        )
        # 今日全 0 空快照不应挡住回退
        db.add(
            LimitUpStat(
                asof=date(2026, 7, 20),
                limit_up_count=0,
                limit_down_count=0,
                max_board=0,
                promote_rate=0.0,
                break_rate=0.0,
            )
        )
        db.commit()
        snap = SentimentService(db).snapshot()
        assert snap["asof"] == "2026-07-14"
        assert snap["limit_up_count"] == 68
        assert len(snap["ladder"]) == 1
    finally:
        db.close()


def test_sentiment_ingest_skips_write_when_source_empty(_db):
    """源返回空列表时不删除、不写入全 0 快照。"""
    from desk_db.models import LimitUpStat

    db = Session(get_engine())
    asof = date(2024, 7, 5)
    db.add(
        LimitUpStat(
            asof=asof,
            limit_up_count=3,
            limit_down_count=0,
            max_board=2,
            promote_rate=0.1,
            break_rate=0.0,
        )
    )
    db.commit()
    client = MockQmtSentimentClient([])
    out = SentimentDailyIngestor(db, client, asof=asof, symbols=["000001.SZ"]).run()
    db.commit()
    assert out.get("skipped_write") is True
    assert out.get("cover") == 0
    stat = db.scalar(select(LimitUpStat).where(LimitUpStat.asof == asof))
    assert stat is not None
    assert stat.limit_up_count == 3
