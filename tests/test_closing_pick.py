"""尾盘选股：扫股与落库。"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from sqlalchemy import select

from desk_closing_pick import ClosingPickService
from desk_closing_pick.screen import eval_buy_signals
from desk_db.models import ClosingBriefRow, ClosingPick, SecurityMeta, StrategyRow, TradeCalendar
from desk_market import MarketService


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
    """默认关闭持仓建议，避免现有用例 content 被附加段改变。"""
    monkeypatch.setattr(
        "desk_positions_advice.advise_advice",
        lambda *a, **k: {"status": "disabled", "source": "live", "items": []},
    )


def _seed_bars(db: Session, symbol: str, n: int = 60, trend: float = 1.01):
    svc = MarketService(db)
    today = date.today()
    price = 10.0
    rows = []
    for i in range(n, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        price *= trend
        rows.append(
            {
                "date": d,
                "open": price * 0.99,
                "high": price * 1.01,
                "low": price * 0.98,
                "close": price,
                "volume": 1e6,
                "amount": price * 1e6,
                "open_hfq": price * 0.99,
                "high_hfq": price * 1.01,
                "low_hfq": price * 0.98,
                "close_hfq": price,
                "volume_hfq": 1e6,
            }
        )
    svc.upsert_daily_bars(symbol, pd.DataFrame(rows))
    db.commit()


def _seed_factor_yaml(db: Session, strategy_id: str, yaml_body: str, roles: list[str] | None = None):
    params = {"roles": roles or []}
    db.add(
        StrategyRow(
            strategy_id=strategy_id,
            name=strategy_id,
            source="yaml",
            version="v0.1",
            status="research",
            lifecycle_stage="incubating",
            yaml_body=yaml_body,
            params_json=json.dumps(params, ensure_ascii=False),
        )
    )
    db.commit()


ALWAYS_BUY_YAML = """
id: close_always_buy
name: always buy close gt 0
kind: factor_rules
buy:
  combine: all
  conditions:
    - left: { factor: CLOSE }
      op: gt
      right: { const: 0 }
sell:
  combine: all
  conditions: []
"""


def test_eval_buy_signals_returns_buy(db: Session):
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])
    out = eval_buy_signals(db, strategy_id="close_always_buy", symbol="600519.SH")
    assert out["ok"] is True
    assert len(out["signals"]) >= 1
    assert out["bar_date"] is not None


def _seed_trade_day(db: Session, day: date | None = None) -> date:
    """将指定日标为交易日，避免周末门闸跳过。"""
    asof = day or date.today()
    db.add(TradeCalendar(cal_date=asof, is_open=True, note=""))
    db.commit()
    return asof


def test_run_scans_universe_and_stores_picks(db: Session):
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.add(SecurityMeta(symbol="000001.SZ", name="平安", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH", trend=1.01)
    _seed_bars(db, "000001.SZ", trend=1.01)
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])

    report = ClosingPickService(db).run(asof=asof)
    assert "close_always_buy" in report.strategy_ids
    assert len(report.stocks) >= 1
    assert report.stocks[0].get("price") is not None
    assert report.stocks[0].get("last_close") == report.stocks[0].get("price")
    picks = db.scalars(select(ClosingPick).where(ClosingPick.asof == asof)).all()
    assert len(picks) >= 1
    briefs = db.scalars(select(ClosingBriefRow).where(ClosingBriefRow.asof == asof)).all()
    assert len(briefs) >= 1


def test_closing_run_appends_positions_advice(db: Session, monkeypatch):
    """尾盘选股正文附带持仓建议段。"""
    monkeypatch.setattr(
        "desk_positions_advice.advise_advice",
        lambda *a, **k: {
            "status": "empty",
            "source": "live",
            "section": "当前无持仓，跳过建议",
            "items": [],
        },
    )
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])

    report = ClosingPickService(db).run(asof=asof)
    assert "持仓建议" in report.content
    assert "无持仓" in report.content


def test_closing_run_advice_exception_still_stores(db: Session, monkeypatch):
    """持仓建议抛错不阻断尾盘选股落库与推送正文。"""

    def boom(*a, **k):
        raise RuntimeError("advice down")

    monkeypatch.setattr("desk_positions_advice.advise_advice", boom)
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])

    report = ClosingPickService(db).run(asof=asof)
    assert len(report.stocks) >= 1
    assert "持仓建议生成失败" in report.content
    assert "advice down" in report.content
    briefs = db.scalars(select(ClosingBriefRow).where(ClosingBriefRow.asof == asof)).all()
    assert len(briefs) >= 1
    extras = json.loads(briefs[0].extras_json or "{}")
    assert extras.get("positions_advice", {}).get("status") == "error"


def test_run_skips_strategies_without_closing_role(db: Session):
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(
        db,
        "no_role",
        ALWAYS_BUY_YAML.replace("close_always_buy", "no_role"),
        roles=[],
    )
    report = ClosingPickService(db).run(asof=asof)
    assert report.strategy_ids == []
    assert report.stocks == []


def test_run_explicit_strategy_ids_bypasses_closing_role(db: Session):
    """显式 strategy_ids 可扫未打 closing 角色的策略。"""
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(
        db,
        "no_role",
        ALWAYS_BUY_YAML.replace("close_always_buy", "no_role"),
        roles=[],
    )
    report = ClosingPickService(db).run(strategy_ids=["no_role"], asof=asof)
    assert "no_role" in report.strategy_ids
    assert len(report.stocks) >= 1
    picks = db.scalars(
        select(ClosingPick).where(
            ClosingPick.asof == asof, ClosingPick.strategy_id == "no_role"
        )
    ).all()
    assert len(picks) >= 1


def test_run_empty_strategy_ids_uses_all_closing(db: Session):
    """strategy_ids=[] 与 None 一样，使用全部 closing 角色策略。"""
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])
    _seed_factor_yaml(
        db,
        "no_role",
        ALWAYS_BUY_YAML.replace("close_always_buy", "no_role"),
        roles=[],
    )

    report = ClosingPickService(db).run(strategy_ids=[], asof=asof)
    assert "close_always_buy" in report.strategy_ids
    assert "no_role" not in report.strategy_ids
    assert len(report.stocks) >= 1


def test_set_closing_role_persists_and_lists(db: Session):
    """set_closing_role 写入 params_json，list_closing_strategy_ids 随之变化。"""
    from desk_strategy import StrategyRegistry

    _seed_factor_yaml(
        db,
        "role_toggle",
        ALWAYS_BUY_YAML.replace("close_always_buy", "role_toggle"),
        roles=[],
    )
    svc = ClosingPickService(db)
    reg = StrategyRegistry(db)
    assert "role_toggle" not in svc.list_closing_strategy_ids()

    meta = reg.set_closing_role("role_toggle", True)
    assert meta is not None
    assert "closing" in (meta.params or {}).get("roles", [])
    row = db.scalars(
        select(StrategyRow).where(StrategyRow.strategy_id == "role_toggle")
    ).one()
    params = json.loads(row.params_json or "{}")
    assert "closing" in params.get("roles", [])
    assert "role_toggle" in svc.list_closing_strategy_ids()

    meta2 = reg.set_closing_role("role_toggle", False)
    assert meta2 is not None
    assert "closing" not in (meta2.params or {}).get("roles", [])
    row2 = db.scalars(
        select(StrategyRow).where(StrategyRow.strategy_id == "role_toggle")
    ).one()
    params2 = json.loads(row2.params_json or "{}")
    assert "closing" not in params2.get("roles", [])
    assert "role_toggle" not in svc.list_closing_strategy_ids()


def test_run_replaces_same_day_brief(db: Session):
    """同日重跑不堆积 ClosingBriefRow。"""
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])
    svc = ClosingPickService(db)
    svc.run(asof=asof)
    svc.run(asof=asof)
    briefs = db.scalars(
        select(ClosingBriefRow).where(
            ClosingBriefRow.asof == asof, ClosingBriefRow.stage == "closing"
        )
    ).all()
    assert len(briefs) == 1


def test_run_no_strategies_explains_reason(db: Session):
    """无 closing 策略且未显式传入时，摘要说明无策略。"""
    asof = _seed_trade_day(db)
    report = ClosingPickService(db).run(asof=asof)
    assert report.stocks == []
    assert report.strategy_ids == []
    assert "没有可跑的策略" in report.content


def test_run_non_trade_day_falls_back_to_previous(db: Session):
    """非交易日手动跑回退到上一交易日并扫描。"""
    from datetime import timedelta

    from desk_db.models import TradeCalendar

    fri = date.today()
    while fri.weekday() != 4:  # Friday
        fri -= timedelta(days=1)
    sat = fri + timedelta(days=1)
    db.add(TradeCalendar(cal_date=fri, is_open=True))
    db.add(TradeCalendar(cal_date=sat, is_open=False))
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])

    report = ClosingPickService(db).run(asof=sat)
    assert report.asof == fri
    assert "非交易日" in report.content
    assert len(report.stocks) >= 1


def test_bind_closing_picks_dedupes_symbols(db: Session):
    """按 score 降序写入自选，同 symbol 去重。"""
    from desk_closing_pick.bind import bind_closing_picks
    from desk_db.models import WatchlistItem

    today = date.today()
    db.add(
        ClosingPick(
            asof=today,
            strategy_id="s1",
            pick_type="stock",
            code="600519.SH",
            name="茅台",
            score=90.0,
            meta_json="{}",
        )
    )
    db.add(
        ClosingPick(
            asof=today,
            strategy_id="s2",
            pick_type="stock",
            code="600519.SH",
            name="茅台",
            score=80.0,
            meta_json="{}",
        )
    )
    db.add(
        ClosingPick(
            asof=today,
            strategy_id="s1",
            pick_type="stock",
            code="000001.SZ",
            name="平安",
            score=70.0,
            meta_json="{}",
        )
    )
    db.commit()
    out = bind_closing_picks(db, asof=today, limit=10)
    assert out["count"] == 2
    assert "600519.SH" in out["added"]
    assert "000001.SZ" in out["added"]
    rows = db.scalars(select(WatchlistItem)).all()
    assert {r.symbol for r in rows} == {"600519.SH", "000001.SZ"}
