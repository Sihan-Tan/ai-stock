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
def client(_db, monkeypatch):
    """
    禁用 lifespan 后台 try_ensure_schema，避免 StaticPool 下与 seed/API 抢连接。

    表已由 `_db` fixture 的 create_all 建好。
    """
    import app as app_pkg

    monkeypatch.setattr(app_pkg, "try_ensure_schema", lambda: True)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _full_bar_row(d: date, close: float = 10.5) -> dict:
    """
    构造 upsert_daily_bars 所需完整行。

    @param d: 交易日
    @param close: 收盘价
    """
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


def _seed_daily_bars(symbol: str, rows: list[dict]) -> int:
    """
    写入日线后关闭 Session，避免 StaticPool 下与 TestClient 抢连接。

    @param symbol: 标的
    @param rows: upsert 行列表
    @returns: 写入行数
    """
    db = get_session_factory()()
    try:
        n = MarketService(db).upsert_daily_bars(symbol, pd.DataFrame(rows))
        db.commit()
        return n
    finally:
        db.close()


def _seed_security_meta_and_board() -> None:
    """写入 meta + 板块成分后关闭 Session。"""
    db = get_session_factory()()
    try:
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
    finally:
        db.close()


def test_security_meta_and_boards_for_symbol(client, _db):
    _seed_security_meta_and_board()

    r = client.get("/api/market/stock/600519.SH/meta")
    assert r.status_code == 200
    assert r.json()["name"] == "贵州茅台"

    b = client.get("/api/market/stock/600519.SH/boards")
    assert b.status_code == 200
    assert b.json()["boards"][0]["board_name"] == "白酒"

    missing = client.get("/api/market/stock/999999.SH/meta")
    assert missing.status_code == 404


def test_bars_daily_period_week(client, _db):
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
    daily_count = _seed_daily_bars("600519.SH", rows)
    assert daily_count == 10

    params = {"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-31"}
    daily = client.get("/api/market/bars/daily", params=params)
    assert daily.status_code == 200
    assert len(daily.json()) == daily_count

    week = client.get("/api/market/bars/daily", params={**params, "period": "week"})
    assert week.status_code == 200
    week_bars = week.json()
    assert isinstance(week_bars, list)
    assert 0 < len(week_bars) < daily_count

    month = client.get("/api/market/bars/daily", params={**params, "period": "month"})
    assert month.status_code == 200
    month_bars = month.json()
    assert isinstance(month_bars, list)
    assert 0 < len(month_bars) < daily_count


def test_technicals_available(client, _db):
    # lookback 相对 today，需 ≥35 根日线落在窗口内
    end = date.today()
    rows = [
        _full_bar_row(end - timedelta(days=i), close=10.0 + (i % 7) * 0.1)
        for i in range(39, -1, -1)
    ]
    assert _seed_daily_bars("600519.SH", rows) == 40

    r = client.get("/api/market/stock/600519.SH/technicals")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert "ma5" in body["latest"]
    assert "macd" in body["latest"]
    assert "rsi14" in body["latest"]


def test_capital_flow_from_db(client, _db):
    """资金流优先读取库内最近数据。"""
    from desk_db.models import CapitalFlowDaily

    db = get_session_factory()()
    try:
        db.add(
            CapitalFlowDaily(
                symbol="600519.SH",
                ts=date.today(),
                main_net=1.2e8,
                super_net=5e7,
                large_net=3e7,
                medium_net=-1e7,
                small_net=-2e7,
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/market/stock/600519.SH/capital-flow")

    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["source"] == "db"
    assert body["latest"]["main_net"] == 1.2e8


def test_capital_flow_live_fallback(client, _db, monkeypatch):
    """库无数据时从实时源读取资金流。"""

    class Fake:
        def fetch_daily(self, symbol: str, days: int = 20):
            return [
                {
                    "ts": date.today(),
                    "main_net": 100.0,
                    "super_net": 10.0,
                    "large_net": 20.0,
                    "medium_net": 30.0,
                    "small_net": 40.0,
                }
            ]

    monkeypatch.setattr(
        "desk_market.stock_detail.get_capital_client",
        lambda: Fake(),
    )

    r = client.get("/api/market/stock/600519.SH/capital-flow")

    assert r.status_code == 200
    assert r.json()["available"] is True
    assert r.json()["source"] == "live"


def test_capital_flow_unavailable(client, _db, monkeypatch):
    """实时资金流失败时返回不可用响应。"""

    class Boom:
        def fetch_daily(self, symbol: str, days: int = 20):
            raise RuntimeError("network")

    monkeypatch.setattr(
        "desk_market.stock_detail.get_capital_client",
        lambda: Boom(),
    )

    r = client.get("/api/market/stock/000001.SZ/capital-flow")

    assert r.status_code == 200
    assert r.json()["available"] is False
