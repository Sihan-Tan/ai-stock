"""生命周期买入闸门。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_broker.paper_runner import PaperStrategyRunner  # noqa: E402
from desk_broker.promotion_gate import buy_block_reason, can_buy  # noqa: E402
from desk_common.contracts import OrderIntent, Side  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_db import Base, get_engine, reset_engine  # noqa: E402
from desk_market import MarketService  # noqa: E402
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


def test_can_buy_stages():
    assert can_buy("probation")
    assert can_buy("production")
    assert not can_buy("incubating")
    assert not can_buy("paper")
    assert not can_buy("retired")
    assert buy_block_reason("incubating")


def _seed(db: Session) -> None:
    svc = MarketService(db)
    today = date.today()
    price = 100.0
    rows = []
    for i in range(80, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        price *= 1.02
        rows.append(
            {
                "date": d,
                "open": price * 0.99,
                "high": price * 1.01,
                "low": price * 0.98,
                "close": price,
                "volume": 1e6,
                "amount": price * 1e6,
                "open_hfq": price * 0.99,
                "high_hfq": price * 1.01,
                "low_hfq": price * 0.98,
                "close_hfq": price,
                "volume_hfq": 1e6,
            }
        )
    svc.upsert_daily_bars("600519.SH", pd.DataFrame(rows))
    db.commit()


def test_runner_blocks_buy_when_incubating(db: Session):
    """孵化阶段 Runner 不下买单（有买信号时 message 含 gate）。"""
    _seed(db)
    reg = StrategyRegistry(db)
    reg.sync_python_to_db()
    reg.set_stage("ma_cross", "incubating", reason="test")
    db.commit()

    runner = PaperStrategyRunner(db)
    assert not can_buy(runner._strategy_stage("ma_cross"))  # noqa: SLF001
    result = runner.run_once(strategy_id="ma_cross", symbol="600519.SH")
    assert result["status"] == "ok"
    assert result.get("lifecycle_stage") == "incubating"
    # 空仓场景下若产生买信号，应被闸门拦住且无成交
    has_buy_sig = any(
        (s.get("side") if isinstance(s, dict) else getattr(s, "side", None))
        in ("buy", Side.BUY)
        for s in (result.get("signals") or [])
    )
    if has_buy_sig:
        assert result.get("orders") == []
        assert "lifecycle gate" in (result.get("message") or "")


def test_probation_can_buy_via_broker(db: Session):
    """试用阶段资金路径仍可下纸单（闸门只拦 Runner 开仓）。"""
    assert can_buy("probation")
    from desk_broker import PaperBroker

    r = PaperBroker(db).place_order(
        OrderIntent(
            symbol="600519.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"g-{uuid4().hex[:8]}",
            mode="paper",
        )
    )
    assert r.status == "filled"
