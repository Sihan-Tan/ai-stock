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
    picks = db.scalars(select(ClosingPick).where(ClosingPick.asof == asof)).all()
    assert len(picks) >= 1
    briefs = db.scalars(select(ClosingBriefRow).where(ClosingBriefRow.asof == asof)).all()
    assert len(briefs) >= 1


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
