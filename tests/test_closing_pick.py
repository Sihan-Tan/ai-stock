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
from desk_db.models import SecurityMeta, StrategyRow
from desk_market import MarketService
from desk_closing_pick.screen import eval_buy_signals


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
