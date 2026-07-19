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
