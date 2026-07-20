"""FactorService.compute_series 契约。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_factor import FactorService


def _bars(n: int = 60) -> pd.DataFrame:
    start = date(2024, 1, 2)
    rows = []
    px = 100.0
    for i in range(n):
        px += 0.5
        d = start + timedelta(days=i)
        rows.append(
            {
                "date": d,
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px,
                "volume": 1000.0,
            }
        )
    return pd.DataFrame(rows)


def test_list_factors_wrapped_shape():
    rows = FactorService().list_factors()
    assert isinstance(rows, list)
    assert rows[0]["name"] == "SMA_5"
    assert "plot" in rows[0]
    assert "default_enabled" in rows[0]


def test_compute_series_returns_bars_and_outputs():
    out = FactorService().compute_series_from_df(_bars(), ["SMA_20", "RSI_14", "MACD"])
    assert out["engine"] in ("talib", "python")
    assert len(out["bars"]) == 60
    assert "sma_20" in out["series"]["SMA_20"]["outputs"]
    assert "rsi_14" in out["series"]["RSI_14"]["outputs"]
    assert set(out["series"]["MACD"]["outputs"]) >= {"macd", "macd_signal", "macd_hist"}
    vals = out["series"]["SMA_20"]["outputs"]["sma_20"]
    assert any(p["v"] is not None for p in vals)


def test_compute_series_unknown_name():
    with pytest.raises(ValueError, match="unknown"):
        FactorService().compute_series_from_df(_bars(30), ["NOPE"])


# --- API tests ---

from fastapi.testclient import TestClient

from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
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


def _seed_daily_bars(symbol: str, rows: list[dict]) -> int:
    """写入日线后关闭 Session，避免 StaticPool 下与 TestClient 抢连接。"""
    db = get_session_factory()()
    try:
        n = MarketService(db).upsert_daily_bars(symbol, pd.DataFrame(rows))
        db.commit()
        return n
    finally:
        db.close()


def _seed_symbol(symbol: str, n: int = 60) -> int:
    """为标的写入 n 根递增生成的日线（相对 today 回看，落在默认查询窗口内）。"""
    end = date.today()
    rows = [
        _full_bar_row(end - timedelta(days=n - 1 - i), close=100.0 + i * 0.5)
        for i in range(n)
    ]
    return _seed_daily_bars(symbol, rows)


def test_api_factors_catalog(client, _db):
    r = client.get("/api/factors")
    assert r.status_code == 200
    body = r.json()
    assert "factors" in body
    names = [f["name"] for f in body["factors"]]
    assert "MACD" in names


def test_api_factors_series_ok(client, _db):
    assert _seed_symbol("600519.SH") == 60
    r = client.get(
        "/api/factors/series",
        params={"symbol": "600519.SH", "names": "SMA_20,RSI_14"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "600519.SH"
    assert "SMA_20" in body["series"]
    assert "RSI_14" in body["series"]
    assert len(body["bars"]) == 60


def test_api_factors_series_no_bars(client, _db):
    r = client.get(
        "/api/factors/series",
        params={"symbol": "600519.SH", "names": "SMA_20"},
    )
    assert r.status_code == 400
    assert "无本地日线" in r.json()["detail"]


def test_api_factors_series_unknown(client, _db):
    _seed_symbol("600519.SH")
    r = client.get(
        "/api/factors/series",
        params={"symbol": "600519.SH", "names": "NOPE"},
    )
    assert r.status_code == 400
    assert "unknown" in r.json()["detail"].lower()
