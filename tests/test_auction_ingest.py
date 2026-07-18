"""竞价快照落库。"""

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
from desk_db.models import AuctionSnapshot, BoardMember, WatchlistItem
from desk_market.auction_ingest import AuctionSnapshotIngestor
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


def test_auction_ingest_writes_watchlist_snapshots(_db):
    """自选标的应根据快照写入竞价涨幅与板块。"""
    db = Session(get_engine())
    asof = date(2024, 7, 5)
    db.add(WatchlistItem(symbol="600519.SH", name="贵州茅台"))
    db.add(
        BoardMember(
            board_code="BK0481",
            board_name="白酒",
            board_type="sector",
            symbol="600519.SH",
            effective_from=asof,
        )
    )
    db.commit()

    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", name="贵州茅台")])
    md._snapshots["600519.SH"] = {
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "last": 109.8,
        "pre_close": 100.0,
        "amount": 1.5e8,
    }

    result = AuctionSnapshotIngestor(db, md, asof=asof).run()
    db.commit()

    assert result["written"] == 1
    row = db.scalar(
        select(AuctionSnapshot).where(
            AuctionSnapshot.asof == asof, AuctionSnapshot.symbol == "600519.SH"
        )
    )
    assert row is not None
    assert row.auction_pct == pytest.approx(0.098)
    assert row.auction_amount == pytest.approx(1.5e8)
    assert row.board_name == "白酒"
