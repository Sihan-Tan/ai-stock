"""回测报告指标应基于真实权益/成交，而非占位公式。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_backtest import (  # noqa: E402
    BacktraderRunner,
    _max_drawdown_from_equity,
    _sharpe_from_equity,
)
from desk_common.contracts import BacktestRequest  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_db import Base, get_engine, reset_engine  # noqa: E402
import desk_db.models  # noqa: F401, E402
from desk_market import MarketService  # noqa: E402


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_max_drawdown_from_peak_trough():
    """100→120→90 的回撤应为 (90/120-1)= -25%。"""
    assert abs(_max_drawdown_from_equity([100.0, 120.0, 90.0]) - (-0.25)) < 1e-9


def test_sharpe_none_on_flat_equity():
    """权益恒定则夏普不可用。"""
    assert _sharpe_from_equity([100.0, 100.0, 100.0]) is None


def test_backtest_report_has_real_metrics(_db):
    """跑 ma_cross 后应有完整权益曲线，且回撤不是 total_return*0.5 占位。"""
    db = Session(get_engine())
    svc = MarketService(db)
    today = date.today()
    price = 100.0
    rows = []
    for i in range(200, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        # 制造几段趋势，便于均线交叉
        phase = (len(rows) // 20) % 2
        price *= 1.012 if phase == 0 else 0.988
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

    report = BacktraderRunner(db).run(
        BacktestRequest(
            strategy_id="ma_cross",
            symbol="600519.SH",
            start=today - timedelta(days=220),
            end=today,
            initial_cash=1_000_000,
        )
    )
    db.commit()

    assert len(report.equity_curve) > 2
    assert all("value" in p and "date" in p for p in report.equity_curve)
    values = [float(p["value"]) for p in report.equity_curve]
    expected_dd = _max_drawdown_from_equity(values)
    assert abs(report.max_drawdown - expected_dd) < 1e-9
    # 旧占位：盈利时 MDD 恒为 0；趋势波段下权益应出现真实回撤
    assert report.max_drawdown < -1e-6
    assert report.trades == len(report.trade_list)
    assert report.trades >= 1
    trade = report.trade_list[0]
    for key in (
        "qty",
        "entry_price",
        "exit_price",
        "dt_open",
        "dt_close",
        "pnlcomm",
        "entry_commission",
        "exit_commission",
        "stamp_duty",
        "fee_total",
    ):
        assert key in trade
    assert float(trade["qty"]) > 0
    assert float(trade["entry_price"]) > 0
    assert float(trade["exit_price"]) > 0
    assert float(trade["entry_commission"]) >= 0
    assert float(trade["exit_commission"]) >= 0
    assert float(trade["stamp_duty"]) >= 0
    assert abs(
        float(trade["fee_total"])
        - (
            float(trade["entry_commission"])
            + float(trade["exit_commission"])
            + float(trade["stamp_duty"])
        )
    ) < 1e-6
