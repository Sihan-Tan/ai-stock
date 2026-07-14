"""核心单元 / 集成测试（SQLite）。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 测试库必须在导入 app 前设置（内存库 + StaticPool，避免文件锁）
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from desk_common.settings import get_settings
from desk_common.symbols import normalize_symbol
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_indicators import compute
import pandas as pd


@pytest.fixture(autouse=True)
def _db():
    get_settings.cache_clear()
    reset_engine()
    try:
        from app.routes import broker as broker_routes

        broker_routes._GATE = None
    except Exception:  # noqa: BLE001
        pass
    Path("data").mkdir(exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def client(_db):
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_normalize_symbol():
    assert normalize_symbol("600519") == "600519.SH"
    assert normalize_symbol("sz000001") == "000001.SZ"


def test_indicators_sma():
    df = pd.DataFrame(
        {
            "open": range(1, 40),
            "high": range(2, 41),
            "low": range(0, 39),
            "close": range(1, 40),
            "volume": [1] * 39,
        }
    )
    out = compute(df, ["SMA_5", "RSI_14"])
    assert "sma_5" in out.columns
    assert out["sma_5"].notna().sum() > 0


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_market_seed_and_watchlist(client):
    assert client.post("/api/market/seed").status_code == 200
    wl = client.get("/api/market/watchlist").json()
    assert len(wl) >= 3


def test_calendar_and_suspension(client):
    assert client.post("/api/calendar/seed").status_code == 200
    today = date.today()
    month = client.get(f"/api/calendar/month?year={today.year}&month={today.month}").json()
    assert len(month) >= 28
    assert isinstance(client.get("/api/calendar/suspensions").json(), list)


def test_sentiment_lhb(client):
    assert client.post("/api/sentiment/seed").status_code == 200
    snap = client.get("/api/sentiment/snapshot").json()
    assert snap["limit_up_count"] >= 1
    assert client.post("/api/lhb/seed").status_code == 200
    assert len(client.get("/api/lhb").json()) >= 1


def test_strategy_python_yaml_agent(client):
    assert client.post("/api/strategies/sync-python").status_code == 200
    assert client.post("/api/strategies/load-yaml-file").status_code == 200
    draft = client.post(
        "/api/strategies/draft",
        json={"payload": {"id": "agent_x", "name": "草稿", "when": {"sma_fast": {"period": 5}}}},
    )
    assert draft.status_code == 200
    assert draft.json()["status"] == "draft"
    promoted = client.post("/api/strategies/agent_x/promote")
    assert promoted.json()["status"] == "research"


def test_backtest_ma_cross(client):
    client.post("/api/market/seed")
    client.post("/api/strategies/sync-python")
    end = date.today()
    start = end - timedelta(days=180)
    r = client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross",
            "symbol": "600519.SH",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "initial_cash": 1_000_000,
        },
    )
    assert r.status_code == 200, r.text
    assert "total_return" in r.json()


def test_paper_order_and_risk(client):
    order = client.post(
        "/api/broker/order",
        json={"symbol": "600519.SH", "side": "buy", "qty": 100, "price": 100, "mode": "paper"},
    )
    assert order.status_code == 200
    assert order.json()["status"] == "filled"
    paper = client.get("/api/broker/paper").json()
    assert paper["cash"] < 1_000_000
    live_reject = client.post(
        "/api/broker/order",
        json={"symbol": "600519.SH", "side": "buy", "qty": 100, "price": 100, "mode": "live"},
    )
    assert live_reject.json()["status"] == "rejected"


def test_ml_both_engines(client):
    a = client.post("/api/ml/train-demo", json={"engine": "lightgbm", "model_id": "lgb_t"})
    b = client.post("/api/ml/train-demo", json={"engine": "xgboost", "model_id": "xgb_t"})
    assert a.status_code == 200 and b.status_code == 200
    models = client.get("/api/ml/models").json()
    engines = {m["engine"] for m in models}
    assert "lightgbm" in engines and "xgboost" in engines


def test_morning_and_ai_skills(client):
    client.post("/api/sentiment/seed")
    client.post("/api/lhb/seed")
    client.post("/api/calendar/seed")
    pre = client.post("/api/morning/preopen")
    post = client.post("/api/morning/post-auction")
    assert pre.status_code == 200
    assert len(post.json()["stocks"]) >= 1
    skills = client.get("/api/ai/skills").json()
    assert any(s["name"] == "desk-readonly" for s in skills)
    chat = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "写一个策略草稿"}]})
    assert chat.status_code == 200
    assert "draft" in chat.text.lower() or "草稿" in chat.text


def test_knowledge_and_review(client):
    up = client.post(
        "/api/knowledge/docs",
        json={"title": "t", "content": "晋级率与情绪退潮", "tags": "情绪"},
    )
    assert up.status_code == 200
    hits = client.post("/api/knowledge/search", json={"query": "晋级率"}).json()
    assert len(hits) >= 1
    rev = client.post(
        "/api/review",
        json={"asof": date.today().isoformat(), "content": "今日复盘", "deviations": [{"type": "slip"}]},
    )
    assert rev.status_code == 200


def test_alerts_log(client):
    r = client.post("/api/alerts/send", json={"title": "测试", "body": "hello", "dedupe_key": "t1"})
    assert r.status_code == 200
    assert len(client.get("/api/alerts").json()) >= 1
