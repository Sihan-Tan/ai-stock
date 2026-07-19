"""核心单元 / 集成测试（SQLite）。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# 测试库必须在导入 app 前设置（内存库 + StaticPool，避免文件锁）
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from desk_common.settings import get_settings
from desk_common.symbols import normalize_symbol
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import AuctionSnapshot, LhbDaily, LhbSeat, LimitUpStat, LimitUpStock, SuspensionEvent
from desk_indicators import compute
from desk_market import MarketService


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


def _session() -> Session:
    return get_session_factory()()


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
    body = r.json()
    assert body["ok"] is True
    assert body["db"] is True
    assert body["db_detail"] == "ok"


def test_try_ensure_schema_soft_fail_unreachable_pg(monkeypatch):
    """Postgres 不可达时 try_ensure_schema 应快速返回 False，不阻塞服务。"""
    import time

    from desk_db import reset_engine, try_ensure_schema

    get_settings.cache_clear()
    reset_engine()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://desk:desk@127.0.0.1:15999/desk")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "2")
    get_settings.cache_clear()
    reset_engine()
    t0 = time.perf_counter()
    ok = try_ensure_schema()
    elapsed = time.perf_counter() - t0
    assert ok is False
    assert elapsed < 15
    reset_engine()
    get_settings.cache_clear()


def test_market_watchlist(client):
    for sym, name in [
        ("600519.SH", "贵州茅台"),
        ("300750.SZ", "宁德时代"),
        ("510300.SH", "沪深300ETF"),
    ]:
        assert client.post("/api/market/watchlist", json={"symbol": sym, "name": name}).status_code == 200
    wl = client.get("/api/market/watchlist").json()
    assert len(wl) >= 3
    assert client.delete("/api/market/watchlist/300750.SZ").status_code == 200
    symbols = {row["symbol"] for row in client.get("/api/market/watchlist").json()}
    assert "300750.SZ" not in symbols
    assert "600519.SH" in symbols


def test_market_watchlist_enriches_quote_and_boards(client, monkeypatch):
    """自选列表应合并实时快照价量与主板块。"""
    from desk_db import get_session_factory
    from desk_db.models import BoardMember
    from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
    import app.routes.market as market_routes

    assert client.post(
        "/api/market/watchlist", json={"symbol": "600519.SH", "name": "贵州茅台"}
    ).status_code == 200

    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", name="贵州茅台")])
    md._snapshots["600519.SH"] = {
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "last": 110.0,
        "pre_close": 100.0,
        "volume": 12_000,
        "turnover_rate": 1.25,
    }
    monkeypatch.setattr(market_routes, "get_market_data", lambda: md)

    db = get_session_factory()()
    try:
        db.add(
            BoardMember(
                board_code="BK0001",
                board_name="白酒",
                board_type="sector",
                symbol="600519.SH",
                effective_from=date(2024, 1, 1),
            )
        )
        db.add(
            BoardMember(
                board_code="BK0002",
                board_name="消费",
                board_type="concept",
                symbol="600519.SH",
                effective_from=date(2024, 1, 1),
            )
        )
        db.commit()
    finally:
        db.close()

    row = next(
        item
        for item in client.get("/api/market/watchlist").json()
        if item["symbol"] == "600519.SH"
    )
    assert row["last"] == 110.0
    assert row["pre_close"] == 100.0
    assert row["pct_chg"] == pytest.approx(10.0)
    assert row["change"] == pytest.approx(10.0)
    assert row["volume"] == 12_000
    assert row["turnover_rate"] == pytest.approx(1.25)
    assert {b["board_name"] for b in row["boards"]} == {"白酒", "消费"}


def test_calendar_and_suspension(client):
    today = date.today()
    db = _session()
    try:
        db.add(
            SuspensionEvent(
                symbol="600000.SH",
                name="示例停牌",
                event_type="suspend",
                effective_date=today,
                reason="重大事项",
                scope="watchlist",
            )
        )
        db.commit()
    finally:
        db.close()
    month = client.get(f"/api/calendar/month?year={today.year}&month={today.month}").json()
    assert len(month) >= 28
    assert isinstance(client.get("/api/calendar/suspensions").json(), list)
    assert len(client.get("/api/calendar/suspensions").json()) >= 1


def test_sentiment_lhb(client):
    today = date.today()
    db = _session()
    try:
        db.add(
            LimitUpStat(
                asof=today,
                limit_up_count=68,
                limit_down_count=12,
                max_board=7,
                promote_rate=0.42,
                break_rate=0.18,
            )
        )
        db.add(
            LimitUpStock(
                asof=today,
                symbol="000001.SZ",
                name="示例连板",
                board_height=7,
                seal_amount=2.1e8,
                concept="AI应用",
                status="sealed",
            )
        )
        row = LhbDaily(asof=today, symbol="300750.SZ", name="宁德时代", reason="日振幅异常", net_buy=1.2e8)
        db.add(row)
        db.flush()
        db.add(
            LhbSeat(
                lhb_id=row.id,
                side="buy",
                seat_name="某证券上海XX路",
                amount=8.2e7,
                is_institution=False,
            )
        )
        db.commit()
    finally:
        db.close()
    snap = client.get("/api/sentiment/snapshot").json()
    assert snap["limit_up_count"] >= 1
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
    db = _session()
    try:
        svc = MarketService(db)
        today = date.today()
        price = 100.0
        rows = []
        for i in range(120, 0, -1):
            d = today - timedelta(days=i)
            if d.weekday() >= 5:
                continue
            price *= 1 + ((hash(f"600519.SH{d}") % 21) - 10) / 1000.0
            o, h, l, c, v = price * 0.99, price * 1.01, price * 0.98, price, 1e6
            rows.append(
                {
                    "date": d,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                    "amount": price * 1e6,
                    "open_hfq": o,
                    "high_hfq": h,
                    "low_hfq": l,
                    "close_hfq": c,
                    "volume_hfq": v,
                }
            )
        svc.upsert_daily_bars("600519.SH", pd.DataFrame(rows))
        db.commit()
    finally:
        db.close()
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


def test_paper_order_and_risk(client, monkeypatch):
    """纸单买入需策略处于试用/主力；未 ARM 的实盘应被拒。"""
    monkeypatch.setenv("RISK_ARMED", "0")
    monkeypatch.setenv("RISK_KILL_SWITCH", "0")
    get_settings.cache_clear()
    client.post("/api/strategies/sync-python")
    sid = get_settings().paper_default_strategy_id or "ma_cross"
    stage = client.post(
        f"/api/strategies/{sid}/lifecycle/stage",
        json={"stage": "probation", "note": "test"},
    )
    assert stage.status_code == 200, stage.text
    order = client.post(
        "/api/broker/order",
        json={
            "symbol": "600519.SH",
            "side": "buy",
            "qty": 100,
            "price": 100,
            "mode": "paper",
            "strategy_id": sid,
        },
    )
    assert order.status_code == 200
    assert order.json()["status"] == "filled", order.json()
    paper = client.get("/api/broker/paper").json()
    assert paper["cash"] < 1_000_000
    live_reject = client.post(
        "/api/broker/order",
        json={"symbol": "600519.SH", "side": "buy", "qty": 100, "price": 100, "mode": "live"},
    )
    assert live_reject.json()["status"] == "rejected"


def test_live_order_respects_settings_size_limits(client, monkeypatch, tmp_path):
    """设置页下单限额对已 ARM 的实盘同样拦截超限单。"""
    # 避免 apply_settings_patch 写回仓库根 .env
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "desk_common.settings_store._env_path",
        lambda: env_file,
    )
    monkeypatch.setenv("RISK_MAX_ORDER_NOTIONAL", "1000")
    monkeypatch.setenv("RISK_MAX_ORDER_POSITION_PCT", "100")
    monkeypatch.setenv("RISK_ARMED", "0")
    get_settings.cache_clear()
    armed = client.post(
        "/api/broker/risk",
        json={
            "armed": True,
            "kill_switch": False,
            "whitelist": ["600519.SH"],
        },
    )
    assert armed.status_code == 200
    # 100 * 100 = 10000 > 单笔最大金额 1000
    oversized = client.post(
        "/api/broker/order",
        json={
            "symbol": "600519.SH",
            "side": "buy",
            "qty": 100,
            "price": 100,
            "mode": "live",
        },
    )
    assert oversized.status_code == 200
    body = oversized.json()
    assert body["status"] == "rejected"
    assert "exceeds" in (body.get("message") or "")


def test_ml_both_engines(client):
    a = client.post("/api/ml/train-demo", json={"engine": "lightgbm", "model_id": "lgb_t"})
    b = client.post("/api/ml/train-demo", json={"engine": "xgboost", "model_id": "xgb_t"})
    assert a.status_code == 200 and b.status_code == 200
    models = client.get("/api/ml/models").json()
    engines = {m["engine"] for m in models}
    assert "lightgbm" in engines and "xgboost" in engines


def test_morning_and_ai_skills(client):
    # 固定周五，避免周末 is_trade_day 门闸导致竞价选拔为空
    asof = date(2024, 7, 5)
    db = _session()
    try:
        db.add(
            LimitUpStat(
                asof=asof,
                limit_up_count=10,
                limit_down_count=2,
                max_board=3,
                promote_rate=0.4,
                break_rate=0.1,
            )
        )
        db.add(
            AuctionSnapshot(
                asof=asof,
                symbol="688001.SH",
                name="示例半导体",
                auction_pct=0.098,
                auction_amount=1.2e8,
                board_code="半导体",
                board_name="半导体",
            )
        )
        db.add(
            AuctionSnapshot(
                asof=asof,
                symbol="300001.SZ",
                name="示例AI",
                auction_pct=0.072,
                auction_amount=0.9e8,
                board_code="人工智能",
                board_name="人工智能",
            )
        )
        db.commit()
    finally:
        db.close()
    pre = client.post("/api/morning/preopen", params={"asof": asof.isoformat()})
    post = client.post("/api/morning/post-auction", params={"asof": asof.isoformat()})
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
