"""尾盘选股 API：run / latest。"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import SecurityMeta, StrategyRow, TradeCalendar
from desk_market import MarketService


ALWAYS_BUY_YAML = """
id: close_api_buy
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


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def client(_db):
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


def _seed_trade_day(db: Session, day: date | None = None) -> date:
    asof = day or date.today()
    db.add(TradeCalendar(cal_date=asof, is_open=True, note=""))
    db.commit()
    return asof


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


def test_closing_run_and_latest(client, _db):
    """POST /run 后 GET /latest 返回 asof/briefs/stocks。"""
    db = Session(get_engine())
    asof = _seed_trade_day(db)
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    db.add(
        StrategyRow(
            strategy_id="close_api_buy",
            name="close_api_buy",
            source="yaml",
            version="v0.1",
            status="research",
            lifecycle_stage="incubating",
            yaml_body=ALWAYS_BUY_YAML,
            params_json=json.dumps({"roles": ["closing"]}, ensure_ascii=False),
        )
    )
    db.commit()
    db.close()

    r = client.post("/api/closing/run", json={"asof": asof.isoformat()})
    assert r.status_code == 200
    body = r.json()
    assert "asof" in body
    assert "content" in body or "stocks" in body

    latest = client.get("/api/closing/latest", params={"asof": asof.isoformat()})
    assert latest.status_code == 200
    data = latest.json()
    assert "briefs" in data
    assert "stocks" in data
    assert data["asof"] == asof.isoformat()
