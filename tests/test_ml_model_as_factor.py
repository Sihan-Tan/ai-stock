"""登记模型删除与放入因子列表。"""

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
from desk_factor import FactorService
from desk_market import MarketService
from desk_ml import MlTrainer


@pytest.fixture()
def _db(tmp_path, monkeypatch):
    get_settings.cache_clear()
    reset_engine()
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_set_as_factor_and_delete(_db):
    db = get_session_factory()()
    try:
        out = MlTrainer(db).fit_demo(engine="lightgbm", model_id="ut_asf")
        db.commit()
        mid = out["model_id"]
        assert mid == "ut_asf"

        row = MlTrainer(db).set_as_factor(mid, True)
        db.commit()
        assert row["as_factor"] is True
        listed = MlTrainer(db).list_models()
        assert any(m["model_id"] == mid and m["as_factor"] for m in listed)

        MlTrainer(db).set_as_factor(mid, False)
        db.commit()
        assert not any(m["model_id"] == mid and m["as_factor"] for m in MlTrainer(db).list_models())

        path = Path(out["path"])
        assert path.exists()
        MlTrainer(db).delete_model(mid)
        db.commit()
        assert not path.exists() or not path.parent.exists()
        assert all(m["model_id"] != mid for m in MlTrainer(db).list_models())
    finally:
        db.close()


def test_delete_missing_raises(_db):
    db = get_session_factory()()
    try:
        with pytest.raises(ValueError, match="model not found"):
            MlTrainer(db).delete_model("no_such")
    finally:
        db.close()


def test_set_as_factor_missing_raises(_db):
    db = get_session_factory()()
    try:
        with pytest.raises(ValueError, match="model not found"):
            MlTrainer(db).set_as_factor("no_such", True)
    finally:
        db.close()


def test_persist_preserves_as_factor(_db):
    db = get_session_factory()()
    try:
        mid = "ut_persist_asf"
        MlTrainer(db).fit_demo(engine="lightgbm", model_id=mid)
        db.commit()
        MlTrainer(db).set_as_factor(mid, True)
        db.commit()

        MlTrainer(db).fit_demo(engine="lightgbm", model_id=mid)
        db.commit()

        listed = MlTrainer(db).list_models()
        match = next(m for m in listed if m["model_id"] == mid)
        assert match["as_factor"] is True
    finally:
        db.close()


def _seed_symbol(symbol: str, n: int = 200) -> None:
    end = date.today()
    rows = []
    for i in range(n):
        close = 100.0 + i * 0.3
        d = end - timedelta(days=n - 1 - i)
        rows.append({
            "date": d, "open": close - 0.2, "high": close + 0.5,
            "low": close - 0.5, "close": close, "volume": 1000.0,
            "amount": close * 1000, "open_hfq": close * 10, "high_hfq": close * 10 + 1,
            "low_hfq": close * 10 - 1, "close_hfq": close * 10, "volume_hfq": 1000.0,
        })
    db = get_session_factory()()
    try:
        MarketService(db).upsert_daily_bars(symbol, pd.DataFrame(rows))
        db.commit()
    finally:
        db.close()


def test_ml_factor_in_list_and_series(_db):
    _seed_symbol("600519.SH", 220)
    db = get_session_factory()()
    try:
        end = date.today()
        start = end - timedelta(days=60)
        MlTrainer(db).fit_symbols(
            ["600519.SH"], start, end, engine="lightgbm", model_id="ut_ml_fac"
        )
        db.commit()

        names_before = [f["name"] for f in FactorService(db).list_factors()]
        assert "ml:ut_ml_fac" not in names_before

        MlTrainer(db).set_as_factor("ut_ml_fac", True)
        db.commit()

        names = [f["name"] for f in FactorService(db).list_factors()]
        assert "ml:ut_ml_fac" in names

        out = FactorService(db).compute_series(
            "600519.SH", ["ml:ut_ml_fac"], start=start, end=end
        )
        pts = out["series"]["ml:ut_ml_fac"]["outputs"]["ml_score"]
        assert len(pts) == len(out["bars"])
        assert any(p["v"] is not None for p in pts)

        with pytest.raises(ValueError, match="not in factor list|as_factor|unknown"):
            FactorService(db).compute_series(
                "600519.SH", ["ml:nope"], start=start, end=end
            )
    finally:
        db.close()


@pytest.fixture()
def client(_db, monkeypatch):
    """FastAPI TestClient（复用内存库 fixture）。"""
    import app as app_pkg
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(app_pkg, "try_ensure_schema", lambda: True)
    with TestClient(app) as c:
        yield c


def test_api_as_factor_then_in_factors(client):
    """fit_demo → as-factor → GET /api/factors 含 ml:{id}。"""
    mid = "api_asf"
    train = client.post("/api/ml/train-demo", json={"engine": "lightgbm", "model_id": mid})
    assert train.status_code == 200, train.text

    r = client.post(f"/api/ml/models/{mid}/as-factor", json={"as_factor": True})
    assert r.status_code == 200, r.text
    assert r.json()["as_factor"] is True

    factors = client.get("/api/factors").json()["factors"]
    names = [f["name"] for f in factors]
    assert f"ml:{mid}" in names


def test_api_delete_removes_model_and_factor(client):
    """DELETE 后 models / factors 均不再含该模型。"""
    mid = "api_del"
    assert client.post("/api/ml/train-demo", json={"engine": "lightgbm", "model_id": mid}).status_code == 200
    assert client.post(f"/api/ml/models/{mid}/as-factor", json={"as_factor": True}).status_code == 200

    deleted = client.delete(f"/api/ml/models/{mid}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["ok"] is True

    models = client.get("/api/ml/models").json()
    assert all(m["model_id"] != mid for m in models)

    names = [f["name"] for f in client.get("/api/factors").json()["factors"]]
    assert f"ml:{mid}" not in names


def test_api_delete_missing_404(client):
    r = client.delete("/api/ml/models/no_such")
    assert r.status_code == 404


def test_api_as_factor_missing_404(client):
    r = client.post("/api/ml/models/no_such/as-factor", json={"as_factor": True})
    assert r.status_code == 404
