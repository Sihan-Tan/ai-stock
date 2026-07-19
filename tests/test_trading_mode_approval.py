"""实盘审批模式。"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["AUTO_EXECUTE_LIVE"] = "0"
os.environ["I_UNDERSTAND_AUTO_LIVE"] = "0"

from desk_broker import BrokerGateway  # noqa: E402
from desk_broker.trading_mode import live_execution_mode  # noqa: E402
from desk_common.contracts import OrderIntent, Side  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_db import Base, get_engine, reset_engine  # noqa: E402
import desk_db.models  # noqa: F401, E402


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


def test_default_live_is_approval():
    get_settings.cache_clear()
    assert live_execution_mode() == "approval"


def test_live_order_awaits_approval(db: Session, monkeypatch):
    monkeypatch.setenv("RISK_ARMED", "1")
    monkeypatch.setenv("RISK_KILL_SWITCH", "0")
    monkeypatch.setenv("RISK_WHITELIST", "")
    get_settings.cache_clear()
    gate = BrokerGateway(db)
    gate.risk.apply_from_settings()
    cid = f"ap-{uuid4().hex[:10]}"
    result = gate.place_order(
        OrderIntent(
            symbol="600519.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=cid,
            mode="live",
        )
    )
    assert result.status == "awaiting_approval"
    items = gate.list_approvals()
    assert any(i["client_order_id"] == cid for i in items)
    approved = gate.approve_order(cid)
    assert approved.status == "filled"
    assert gate.list_approvals() == []
