"""多股日线 ML 训练。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
from desk_market import MarketService
from desk_ml import MlTrainer


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def _full_bar_row(d: date, close: float = 10.5) -> dict:
    return {
        "date": d,
        "open": close - 0.2,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 1000 + (close % 10) * 10,
        "amount": close * 1000,
        "open_hfq": close * 10,
        "high_hfq": close * 10 + 1,
        "low_hfq": close * 10 - 1,
        "close_hfq": close * 10,
        "volume_hfq": 1000,
    }


def _seed_symbol(symbol: str, n: int = 200) -> None:
    end = date.today()
    rows = [
        _full_bar_row(end - timedelta(days=n - 1 - i), close=100.0 + i * 0.3 + (i % 7) * 0.1)
        for i in range(n)
    ]
    db = get_session_factory()()
    try:
        MarketService(db).upsert_daily_bars(symbol, pd.DataFrame(rows))
        db.commit()
    finally:
        db.close()


def test_fit_symbols_trains_on_seeded_bars(_db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_symbol("600519.SH", 200)
    end = date.today()
    start = end - timedelta(days=90)

    db = get_session_factory()()
    try:
        out = MlTrainer(db).fit_symbols(
            ["600519.SH"],
            start,
            end,
            engine="lightgbm",
            model_id="ut_lgb",
        )
        db.commit()
    finally:
        db.close()

    assert out["engine"] == "lightgbm"
    assert out["symbols_used"] == ["600519.SH"]
    assert out["metrics"]["n_samples"] >= 30
    assert "train_accuracy" in out["metrics"]
    assert len(out["features"]) >= 5


def test_fit_symbols_skips_empty(_db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    end = date.today()
    start = end - timedelta(days=30)
    db = get_session_factory()()
    try:
        with pytest.raises(ValueError, match="无可用训练样本"):
            MlTrainer(db).fit_symbols(["999999.SH"], start, end, engine="lightgbm")
    finally:
        db.close()


def test_api_train_symbols(_db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_symbol("600519.SH", 200)
    import app as app_pkg

    monkeypatch.setattr(app_pkg, "try_ensure_schema", lambda: True)
    from fastapi.testclient import TestClient
    from app.main import app

    end = date.today()
    start = end - timedelta(days=90)
    with TestClient(app) as client:
        r = client.post(
            "/api/ml/train-symbols",
            json={
                "symbols": ["600519.SH"],
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "lightgbm" in body
    assert "xgboost" in body
    assert body["lightgbm"]["metrics"]["n_samples"] >= 30
