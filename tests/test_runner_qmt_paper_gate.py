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
    Base.metadata.create_all(bind=get_engine())
    session = Session(get_engine())
    yield session
    session.close()
    reset_engine()
    get_settings.cache_clear()


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
