"""早盘选股：非交易日回退上一交易日。"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import AuctionSnapshot, TradeCalendar
from desk_morning_brief import MorningBriefService


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    yield Session(bind=get_engine())
    reset_engine()
    get_settings.cache_clear()


def test_resolve_asof_falls_back_on_rest_day(db: Session):
    """休息日 resolve 到上一交易日。"""
    fri = date.today()
    while fri.weekday() != 4:
        fri -= timedelta(days=1)
    sat = fri + timedelta(days=1)
    db.add(TradeCalendar(cal_date=fri, is_open=True))
    db.add(TradeCalendar(cal_date=sat, is_open=False))
    db.commit()

    asof, note = MorningBriefService(db).resolve_asof(sat)
    assert asof == fri
    assert "非交易日" in note


def test_post_auction_uses_previous_trade_day_snapshots(db: Session):
    """休息日竞价选拔读取上一交易日快照。"""
    fri = date.today()
    while fri.weekday() != 4:
        fri -= timedelta(days=1)
    sat = fri + timedelta(days=1)
    db.add(TradeCalendar(cal_date=fri, is_open=True))
    db.add(TradeCalendar(cal_date=sat, is_open=False))
    db.add(
        AuctionSnapshot(
            asof=fri,
            symbol="600519.SH",
            name="茅台",
            auction_pct=0.05,
            auction_amount=1e8,
            auction_price=105.0,
            board_code="白酒",
            board_name="白酒",
        )
    )
    db.add(
        AuctionSnapshot(
            asof=fri,
            symbol="000001.SZ",
            name="平安",
            auction_pct=-0.02,
            auction_amount=5e7,
            auction_price=10.0,
            board_code="银行",
            board_name="银行",
        )
    )
    db.commit()

    report = MorningBriefService(db).run_post_auction(sat)
    assert report.asof == fri
    assert len(report.stocks) >= 1
    assert report.stocks[0]["symbol"] == "600519.SH"
    assert report.stocks[0].get("price") == 105.0
    assert all(float(s["auction_pct"]) > 0 for s in report.stocks)


def test_latest_skips_rest_day_skip_brief(db: Session):
    """
    休息日若仅有旧「跳过」摘要，latest 仍应回退到上一交易日的板块/个股。
    """
    from app.routes.morning import morning_latest
    from desk_db.models import MorningBriefRow, MorningStrongPick

    fri = date.today()
    while fri.weekday() != 4:
        fri -= timedelta(days=1)
    sat = fri + timedelta(days=1)
    db.add(TradeCalendar(cal_date=fri, is_open=True))
    db.add(TradeCalendar(cal_date=sat, is_open=False))
    db.add(
        MorningBriefRow(
            asof=sat,
            stage="preopen",
            content=f"{sat} 非交易日，跳过晨会开盘前篇。",
            extras_json="{}",
        )
    )
    db.add(
        MorningStrongPick(
            asof=fri,
            pick_type="stock",
            code="600519.SH",
            name="茅台",
            score=88.0,
            meta_json='{"symbol":"600519.SH","auction_pct":0.05}',
        )
    )
    db.add(
        MorningStrongPick(
            asof=fri,
            pick_type="board",
            code="白酒",
            name="白酒",
            score=10.0,
            meta_json='{"board":"白酒","avg_pct":0.05}',
        )
    )
    db.commit()

    body = morning_latest(asof=sat, db=db)
    assert body["asof"] == fri.isoformat()
    assert len(body["stocks"]) >= 1
    assert len(body["boards"]) >= 1
