"""纸交易费用与市值权益对齐回测口径。"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_broker import PaperBroker  # noqa: E402
from desk_common.contracts import OrderIntent, Side  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_common.trading_cost import (  # noqa: E402
    apply_slippage,
    calc_buy_commission,
    calc_sell_fees,
)
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


def test_buy_deducts_commission_and_marks_equity(db: Session):
    """买入后现金减少 = 滑点后成交额 + 佣金；权益含持仓市值。"""
    broker = PaperBroker(db)
    before = broker.summary()
    cash0 = float(before["cash"])
    settings = get_settings()
    raw = 10.0
    qty = 1000.0
    fill = apply_slippage(raw, "buy", slippage=settings.backtest_slippage)
    notional = fill * qty
    comm = calc_buy_commission(
        notional,
        buy_commission=settings.backtest_buy_commission,
        min_commission=settings.backtest_min_commission,
    )
    result = broker.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=qty,
            price=raw,
            client_order_id=f"t-{uuid4().hex[:8]}",
            mode="paper",
        )
    )
    assert result.status == "filled"
    after = broker.summary()
    assert abs(float(after["cash"]) - (cash0 - notional - comm)) < 1e-6
    # 无行情时用成本价标记，权益 ≈ 初始现金 - 佣金（滑点买卖对称前买贵）
    assert float(after["equity"]) < cash0
    assert len(after["positions"]) == 1


def test_sell_deducts_stamp_duty(db: Session):
    """卖出扣佣金与印花税。"""
    broker = PaperBroker(db)
    settings = get_settings()
    buy = broker.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=1000,
            price=10.0,
            client_order_id=f"b-{uuid4().hex[:8]}",
            mode="paper",
        )
    )
    assert buy.status == "filled"
    mid = broker.summary()
    cash_mid = float(mid["cash"])
    raw = 10.0
    qty = 1000.0
    fill = apply_slippage(raw, "sell", slippage=settings.backtest_slippage)
    notional = fill * qty
    sell_comm, stamp = calc_sell_fees(
        notional,
        sell_commission=settings.backtest_sell_commission,
        stamp_duty=settings.backtest_stamp_duty,
        min_commission=settings.backtest_min_commission,
    )
    sell = broker.place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.SELL,
            qty=qty,
            price=raw,
            client_order_id=f"s-{uuid4().hex[:8]}",
            mode="paper",
        )
    )
    assert sell.status == "filled"
    after = broker.summary()
    assert abs(float(after["cash"]) - (cash_mid + notional - sell_comm - stamp)) < 1e-6
    assert after["positions"] == []
