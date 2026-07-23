"""Runner 调度、纸单闸门、QMT Mock 路径。"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["QMT_FORCE_MOCK"] = "1"
os.environ["AUTO_EXECUTE_LIVE"] = "0"
os.environ["I_UNDERSTAND_AUTO_LIVE"] = "0"
os.environ["PAPER_DEFAULT_STRATEGY_ID"] = "ma_cross"

from desk_broker import BrokerGateway  # noqa: E402
from desk_broker.runner_scheduler import build_paper_runner_scheduler, get_runner_status  # noqa: E402
from desk_common.contracts import OrderIntent, Side  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_db import Base, get_engine, reset_engine  # noqa: E402
from desk_strategy import StrategyRegistry  # noqa: E402
import desk_db.models  # noqa: F401, E402
import desk_strategy.strategies  # noqa: F401, E402


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    try:
        from app.routes import broker as broker_routes

        broker_routes._GATE = None
    except Exception:  # noqa: BLE001
        pass
    Base.metadata.create_all(bind=get_engine())
    session = Session(get_engine())
    yield session
    session.close()
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def client(db: Session):
    from pathlib import Path

    from fastapi.testclient import TestClient

    Path("data").mkdir(exist_ok=True)
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_runner_scheduler_dry_run_job_ids():
    sched, ids = build_paper_runner_scheduler(enabled=True, dry_run=True)
    assert "paper_runner_interval" in ids
    assert "paper_runner_close" in ids
    assert len(sched.get_jobs()) == 2


def test_runner_status_shape():
    st = get_runner_status()
    assert "enabled" in st
    assert "strategy_id" in st
    assert "last_run" in st


def test_paper_buy_blocked_when_default_incubating(db: Session):
    """手动纸买经网关：默认策略孵化阶段应拒绝。"""
    reg = StrategyRegistry(db)
    reg.sync_python_to_db()
    reg.set_stage("ma_cross", "incubating", reason="test")
    db.commit()
    get_settings.cache_clear()

    gate = BrokerGateway(db)
    result = gate.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"g-{uuid4().hex[:8]}",
            strategy_id="ma_cross",
            mode="paper",
        )
    )
    assert result.status == "rejected"
    assert "lifecycle gate" in (result.message or "")


def test_paper_buy_allowed_on_probation(db: Session):
    reg = StrategyRegistry(db)
    reg.sync_python_to_db()
    reg.set_stage("ma_cross", "probation", reason="test")
    db.commit()
    get_settings.cache_clear()

    gate = BrokerGateway(db)
    result = gate.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"g-{uuid4().hex[:8]}",
            strategy_id="ma_cross",
            mode="paper",
        )
    )
    assert result.status == "filled"


def test_manual_paper_buy_skips_lifecycle(db: Session):
    """监控页添加股票：strategy_id=manual 即使默认策略孵化也可建仓。"""
    reg = StrategyRegistry(db)
    reg.sync_python_to_db()
    reg.set_stage("ma_cross", "incubating", reason="test")
    db.commit()
    get_settings.cache_clear()

    gate = BrokerGateway(db)
    result = gate.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"m-{uuid4().hex[:8]}",
            strategy_id="manual",
            mode="paper",
        )
    )
    assert result.status == "filled", result.message


def test_manual_paper_buy_skips_size_limits(db: Session):
    """手动建仓不受单笔限额限制（高价股 100 股常超 5 万上限）。"""
    get_settings.cache_clear()
    gate = BrokerGateway(db)
    # 1800 * 100 = 18 万 >> RISK_MAX_ORDER_NOTIONAL 默认 5 万
    result = gate.place_order(
        OrderIntent(
            symbol="600519.SH",
            side=Side.BUY,
            qty=100,
            price=1800.0,
            client_order_id=f"hi-{uuid4().hex[:8]}",
            strategy_id="manual",
            mode="paper",
        )
    )
    assert result.status == "filled", result.message
    summary = gate.paper.summary()
    held = {p["symbol"]: p for p in summary["positions"]}
    assert "600519.SH" in held
    assert held["600519.SH"]["qty"] == 100


def test_seed_paper_position_api(client):
    """POST /api/broker/paper/seed 规范化代码并写入持仓。"""
    r = client.post(
        "/api/broker/paper/seed",
        json={"symbol": "600519", "price": 1800.0, "qty": 100},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "filled", body
    assert body["symbol"] == "600519.SH"
    paper = client.get("/api/broker/paper").json()
    assert any(p["symbol"] == "600519.SH" and p["qty"] == 100 for p in paper["positions"])


def test_sell_paper_position_api(client):
    """POST /api/broker/paper/sell 可全平持仓。"""
    seed = client.post(
        "/api/broker/paper/seed",
        json={"symbol": "600000", "price": 10.0, "qty": 200},
    )
    assert seed.status_code == 200, seed.text
    assert seed.json()["status"] == "filled", seed.json()

    sell = client.post(
        "/api/broker/paper/sell",
        json={"symbol": "600000", "price": 10.5, "qty": 200},
    )
    assert sell.status_code == 200, sell.text
    body = sell.json()
    assert body["status"] == "filled", body
    assert body["symbol"] == "600000.SH"
    assert body["qty"] == 200

    paper = client.get("/api/broker/paper").json()
    assert not any(p["symbol"] == "600000.SH" and p["qty"] > 0 for p in paper["positions"])


def test_sell_paper_partial_qty(client):
    """卖出可指定部分数量。"""
    seed = client.post(
        "/api/broker/paper/seed",
        json={"symbol": "601318", "price": 50.0, "qty": 300},
    )
    assert seed.json()["status"] == "filled", seed.json()
    sell = client.post(
        "/api/broker/paper/sell",
        json={"symbol": "601318", "price": 51.0, "qty": 100},
    )
    assert sell.json()["status"] == "filled", sell.json()
    paper = client.get("/api/broker/paper").json()
    held = next(p for p in paper["positions"] if p["symbol"] == "601318.SH")
    assert held["qty"] == 200


def test_max_positions_blocks_new_symbol(db: Session, monkeypatch):
    """达到最多持仓只数后，买入新标的被拒；加仓已有标的仍可通过。"""
    monkeypatch.setenv("RISK_MAX_POSITIONS", "1")
    get_settings.cache_clear()
    gate = BrokerGateway(db)
    first = gate.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"p1-{uuid4().hex[:8]}",
            strategy_id="manual",
            mode="paper",
        )
    )
    assert first.status == "filled", first.message
    blocked = gate.place_order(
        OrderIntent(
            symbol="600519.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"p2-{uuid4().hex[:8]}",
            strategy_id="manual",
            mode="paper",
        )
    )
    assert blocked.status == "rejected"
    assert "max positions" in (blocked.message or "")
    add_more = gate.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"p3-{uuid4().hex[:8]}",
            strategy_id="manual",
            mode="paper",
        )
    )
    assert add_more.status == "filled", add_more.message


def test_paper_sell_not_gated(db: Session):
    """卖出不受生命周期买闸门限制（无持仓则 insufficient）。"""
    gate = BrokerGateway(db)
    result = gate.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.SELL,
            qty=100,
            price=10.0,
            client_order_id=f"s-{uuid4().hex[:8]}",
            mode="paper",
        )
    )
    assert result.status == "rejected"
    assert "lifecycle" not in (result.message or "").lower()


def test_qmt_ping_reports_force_mock(db: Session):
    gate = BrokerGateway(db)
    ping = gate.live.ping()
    assert ping.get("force_mock") is True
    assert "real_ready" in ping


def test_live_positions_api_returns_local_when_unconfigured(client, db: Session, monkeypatch):
    """未配置账号时 /live/positions 回退本地 live_positions。"""
    from desk_db.models import LivePosition

    monkeypatch.setenv("QMT_ACCOUNT_ID", "")
    monkeypatch.setenv("QMT_USERDATA_PATH", "")
    get_settings.cache_clear()
    try:
        from app.routes import broker as broker_routes

        broker_routes._GATE = None
    except Exception:  # noqa: BLE001
        pass

    db.add(LivePosition(symbol="600519.SH", qty=200, cost=1800.0))
    db.commit()
    r = client.get("/api/broker/live/positions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "local_db"
    assert any(p["symbol"] == "600519.SH" and p["qty"] == 200 for p in body["positions"])


def test_live_positions_query_ignores_force_mock(db: Session, monkeypatch):
    """force_mock 为 True 时仍应允许读 QMT 持仓（不拦查询）。"""
    monkeypatch.setenv("QMT_FORCE_MOCK", "1")
    monkeypatch.setenv("QMT_ACCOUNT_ID", "8880309163")
    monkeypatch.setenv("QMT_USERDATA_PATH", r"D:\dummy\userdata_mini")
    get_settings.cache_clear()
    gate = BrokerGateway(db)
    assert gate.live._qmt_query_ready() is True
    assert gate.live._real_qmt_ready() is False

    fake_pos = [
        {
            "symbol": "600519.SH",
            "qty": 100.0,
            "can_use_qty": 100.0,
            "cost": 10.0,
            "market_value": 1000.0,
            "frozen_qty": 0.0,
            "yesterday_qty": 100.0,
        }
    ]
    monkeypatch.setattr(
        "desk_broker.qmt_trader.connect_qmt",
        lambda **kwargs: {"connected": True},
    )
    monkeypatch.setattr(
        "desk_broker.qmt_trader.query_stock_positions",
        lambda: fake_pos,
    )
    monkeypatch.setattr(
        "desk_broker.qmt_trader.query_stock_asset",
        lambda: {"cash": 1.0, "market_value": 1000.0, "total_asset": 1001.0},
    )
    snap = gate.live.account_snapshot()
    assert snap["source"] == "qmt"
    assert snap["positions"][0]["symbol"] == "600519.SH"
    assert snap["positions"][0].get("strategy_id")
    assert "sold" in snap
    assert "FORCE_MOCK" in (snap.get("message") or "")
