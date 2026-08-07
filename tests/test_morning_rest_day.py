"""早盘选股：非交易日回退上一交易日。"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import AuctionSnapshot, MorningBriefRow, TradeCalendar
from desk_morning_brief import MorningBriefService
from sqlalchemy import select


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    yield Session(bind=get_engine())
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _disable_positions_advice(monkeypatch):
    """默认关闭持仓建议，避免现有用例 content/extras 被附加段改变。"""
    monkeypatch.setattr(
        "desk_positions_advice.advise_advice",
        lambda *a, **k: {"status": "disabled", "source": "live", "items": []},
    )
    # 避免本机开启自动精选/飞书时单测卡住外网 LLM 或 Webhook
    monkeypatch.setenv("RESEARCH_REFINE_AUTO", "0")
    monkeypatch.setenv("FEISHU_ALERT_ENABLED", "0")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "desk_morning_brief.maybe_auto_refine",
        lambda *a, **k: None,
    )


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

    from desk_ai.refine import MORNING_STOCK_STRATEGY_ID
    from desk_db.models import MorningStrongPick
    from desk_morning_brief import MORNING_BOARD_STRATEGY_ID

    picks = db.scalars(
        select(MorningStrongPick).where(MorningStrongPick.asof == fri)
    ).all()
    assert any(p.pick_type == "stock" and p.strategy_id == MORNING_STOCK_STRATEGY_ID for p in picks)
    assert any(p.pick_type == "board" and p.strategy_id == MORNING_BOARD_STRATEGY_ID for p in picks)


def test_post_auction_upsert_no_duplicate_rows(db: Session):
    """同日重跑竞价选拔不产生重复候选行，并清理孤儿。"""
    from desk_ai.refine import MORNING_STOCK_STRATEGY_ID
    from desk_db.models import MorningStrongPick

    asof = date.today()
    while asof.weekday() >= 5:
        asof -= timedelta(days=1)
    db.add(TradeCalendar(cal_date=asof, is_open=True))
    db.add(
        AuctionSnapshot(
            asof=asof,
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
        MorningStrongPick(
            asof=asof,
            pick_type="stock",
            code="999999.SH",
            name="孤儿",
            score=1.0,
            strategy_id=MORNING_STOCK_STRATEGY_ID,
            meta_json="{}",
        )
    )
    db.commit()

    svc = MorningBriefService(db)
    svc.run_post_auction(asof)
    svc.run_post_auction(asof)
    picks = db.scalars(
        select(MorningStrongPick).where(MorningStrongPick.asof == asof)
    ).all()
    codes = [(p.pick_type, p.code) for p in picks]
    assert len(codes) == len(set(codes))
    assert ("stock", "600519.SH") in codes
    assert ("stock", "999999.SH") not in codes
    stock = next(p for p in picks if p.pick_type == "stock")
    assert stock.strategy_id == MORNING_STOCK_STRATEGY_ID
    assert stock.score > 0



def test_post_auction_appends_positions_advice(db: Session, monkeypatch):
    """竞价强势正文附带持仓建议段。"""
    monkeypatch.setattr(
        "desk_positions_advice.advise_advice",
        lambda *a, **k: {
            "status": "empty",
            "source": "live",
            "section": "当前无持仓，跳过建议",
            "items": [],
        },
    )
    asof = date.today()
    while asof.weekday() >= 5:
        asof -= timedelta(days=1)
    db.add(TradeCalendar(cal_date=asof, is_open=True))
    db.add(
        AuctionSnapshot(
            asof=asof,
            symbol="600519.SH",
            name="茅台",
            auction_pct=0.05,
            auction_amount=1e8,
            auction_price=105.0,
            board_code="白酒",
            board_name="白酒",
        )
    )
    db.commit()

    MorningBriefService(db).run_post_auction(asof)
    brief = db.scalars(
        select(MorningBriefRow).where(
            MorningBriefRow.asof == asof,
            MorningBriefRow.stage == "post_auction",
        )
    ).one()
    assert "持仓建议" in brief.content
    assert "无持仓" in brief.content
    extras = json.loads(brief.extras_json or "{}")
    assert extras.get("positions_advice", {}).get("status") == "empty"


def test_post_auction_advice_exception_still_stores(db: Session, monkeypatch):
    """持仓建议抛错不阻断早盘竞价选拔落库。"""

    def boom(*a, **k):
        raise RuntimeError("advice down")

    monkeypatch.setattr("desk_positions_advice.advise_advice", boom)
    asof = date.today()
    while asof.weekday() >= 5:
        asof -= timedelta(days=1)
    db.add(TradeCalendar(cal_date=asof, is_open=True))
    db.add(
        AuctionSnapshot(
            asof=asof,
            symbol="600519.SH",
            name="茅台",
            auction_pct=0.05,
            auction_amount=1e8,
            auction_price=105.0,
            board_code="白酒",
            board_name="白酒",
        )
    )
    db.commit()

    report = MorningBriefService(db).run_post_auction(asof)
    assert len(report.stocks) >= 1
    brief = db.scalars(
        select(MorningBriefRow).where(
            MorningBriefRow.asof == asof,
            MorningBriefRow.stage == "post_auction",
        )
    ).one()
    assert "持仓建议生成失败" in brief.content
    assert "advice down" in brief.content
    extras = json.loads(brief.extras_json or "{}")
    assert extras.get("positions_advice", {}).get("status") == "error"
    assert extras.get("stocks")


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
