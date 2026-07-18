"""A 股回测费用模型。"""

from __future__ import annotations

from desk_backtest.commission import (
    AShareCommission,
    calc_buy_commission,
    calc_sell_fees,
)


def test_buy_applies_min_commission():
    """小额买入佣金不足 5 元时按最低收费。"""
    assert abs(calc_buy_commission(10_000, buy_commission=0.00025, min_commission=5.0) - 5.0) < 1e-9
    comm = AShareCommission(
        buy_commission=0.00025,
        sell_commission=0.00025,
        stamp_duty=0.001,
        min_commission=5.0,
    )
    assert abs(comm._getcommission(100, 100.0, False) - 5.0) < 1e-9


def test_sell_includes_stamp_duty_and_min_commission():
    """卖出 = max(成交额×卖佣, 最低佣金) + 成交额×印花税。"""
    exit_comm, stamp = calc_sell_fees(
        10_000, sell_commission=0.00025, stamp_duty=0.001, min_commission=5.0
    )
    assert abs(exit_comm - 5.0) < 1e-9
    assert abs(stamp - 10.0) < 1e-9
    comm = AShareCommission(
        buy_commission=0.00025,
        sell_commission=0.00025,
        stamp_duty=0.001,
        min_commission=5.0,
    )
    fee = comm._getcommission(-100, 100.0, False)
    assert abs(fee - 15.0) < 1e-9


def test_large_buy_uses_rate():
    """大额买入按费率、不低于最低佣金。"""
    assert (
        abs(calc_buy_commission(1_000_000, buy_commission=0.00025, min_commission=5.0) - 250.0)
        < 1e-9
    )
