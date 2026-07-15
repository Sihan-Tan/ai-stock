"""龙虎榜日终幂等。"""

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
from desk_db.models import LhbSeat
from desk_lhb import FakeLhbClient, LhbDailyIngestor, LhbService


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_lhb_ingest_replace(_db):
    db = Session(get_engine())
    asof = date(2024, 7, 4)
    client = FakeLhbClient(
        [
            {
                "symbol": "300750.SZ",
                "name": "宁德时代",
                "reason": "振幅",
                "net_buy": 1e8,
                "seats": [
                    {"side": "buy", "seat_name": "某营业部", "amount": 1},
                    {"side": "sell", "seat_name": "机构专用", "amount": 2},
                ],
            }
        ]
    )
    LhbDailyIngestor(db, client, asof=asof).run()
    db.commit()
    rows = LhbService(db).by_date(asof)
    assert len(rows) == 1
    assert len(rows[0]["seats"]) == 2
    assert rows[0]["seats"][1]["is_institution"] is True
    n1 = db.scalar(select(func.count()).select_from(LhbSeat))
    LhbDailyIngestor(db, client, asof=asof).run()
    db.commit()
    n2 = db.scalar(select(func.count()).select_from(LhbSeat))
    assert n1 == n2 == 2
