"""Market API contracts。"""

from __future__ import annotations

import os
from datetime import date
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
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_bars_daily_adj_and_jobs_status(client, _db, monkeypatch):
    from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
    import app.routes.market as market_routes

    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date.today(),
        qfq={"open": 10, "high": 10, "low": 10, "close": 10.5, "volume": 1, "amount": 1},
        hfq={"open": 100, "high": 100, "low": 100, "close": 105, "volume": 1},
    )
    monkeypatch.setattr(market_routes, "get_market_data", lambda: md)

    db = Session(get_engine())
    MarketService(db).upsert_daily_bars(
        "600519.SH",
        pd.DataFrame(
            [
                {
                    "date": date(2024, 1, 2),
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "volume": 1,
                    "amount": 1,
                    "open_hfq": 100,
                    "high_hfq": 110,
                    "low_hfq": 90,
                    "close_hfq": 105,
                    "volume_hfq": 1,
                }
            ]
        ),
    )
    db.commit()

    r = client.get(
        "/api/market/bars/daily",
        params={"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-03"},
    )
    assert r.status_code == 200
    assert r.json()[0]["close"] == 10.5
    r2 = client.get(
        "/api/market/bars/daily",
        params={"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-03", "adj": "hfq"},
    )
    assert r2.json()[0]["close"] == 105.0
    r3 = client.get(
        "/api/market/bars/daily",
        params={"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-03", "adj": "qfq"},
    )
    assert r3.json()[0]["close"] == 10.5

    assert client.post("/api/market/jobs/daily-sync").status_code == 200
    assert client.post("/api/market/jobs/minute-sync").status_code == 200
    assert client.post("/api/market/jobs/backfill").status_code == 200
    st = client.get("/api/market/jobs/status")
    assert st.status_code == 200
    assert isinstance(st.json(), list)
