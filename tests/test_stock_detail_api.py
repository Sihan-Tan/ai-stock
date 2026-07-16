"""Stock detail API contracts。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BoardMember, SecurityMeta
from desk_market import MarketService


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
    from app.main import app

    with TestClient(app) as c:
        yield c


def _full_bar_row(d: date, close: float = 10.5) -> dict:
    """构造 upsert_daily_bars 所需完整行。"""
    return {
        "date": d,
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": close,
        "volume": 1000,
        "amount": 10500,
        "open_hfq": 100.0,
        "high_hfq": 110.0,
        "low_hfq": 95.0,
        "close_hfq": close * 10,
        "volume_hfq": 1000,
    }


def test_security_meta_and_boards_for_symbol(client, _db):
    db = get_session_factory()()
    db.add(SecurityMeta(symbol="600519.SH", name="贵州茅台", status="listed"))
    db.add(
        BoardMember(
            board_code="BK0001",
            board_name="白酒",
            board_type="sector",
            symbol="600519.SH",
            effective_from=date(2020, 1, 1),
        )
    )
    db.commit()
    db.close()

    r = client.get("/api/market/stock/600519.SH/meta")
    assert r.status_code == 200
    assert r.json()["name"] == "贵州茅台"

    b = client.get("/api/market/stock/600519.SH/boards")
    assert b.status_code == 200
    assert b.json()["boards"][0]["board_name"] == "白酒"

    missing = client.get("/api/market/stock/999999.SH/meta")
    assert missing.status_code == 404


def test_bars_daily_period_week(client, _db):
    db = get_session_factory()()
    svc = MarketService(db)
    # 2024-01 约 10 个交易日（跳过周末）
    days = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
        date(2024, 1, 10),
        date(2024, 1, 11),
        date(2024, 1, 12),
        date(2024, 1, 15),
    ]
    rows = [_full_bar_row(d, close=10.0 + i * 0.1) for i, d in enumerate(days)]
    assert svc.upsert_daily_bars("600519.SH", pd.DataFrame(rows)) == 10
    db.commit()
    db.close()

    r = client.get(
        "/api/market/bars/daily",
        params={
            "symbol": "600519.SH",
            "from": "2024-01-01",
            "to": "2024-01-31",
            "period": "week",
        },
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) < 10


def test_technicals_available(client, _db):
    db = get_session_factory()()
    svc = MarketService(db)
    # lookback 相对 today，需 ≥35 根连续日线落在窗口内
    end = date.today()
    rows = [_full_bar_row(end - timedelta(days=i), close=10.0 + (i % 7) * 0.1) for i in range(39, -1, -1)]
    assert svc.upsert_daily_bars("600519.SH", pd.DataFrame(rows)) == 40
    db.commit()
    db.close()

    r = client.get("/api/market/stock/600519.SH/technicals")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert "ma5" in body["latest"]
    assert "macd" in body["latest"]
    assert "rsi14" in body["latest"]
