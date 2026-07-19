"""A 股交易成本：回测与纸交易共用。"""

from __future__ import annotations

from typing import Literal


def calc_buy_commission(
    turnover: float,
    *,
    buy_commission: float,
    min_commission: float,
) -> float:
    """
    买入佣金。

    @param turnover: 成交额
    @param buy_commission: 买入费率
    @param min_commission: 最低佣金
    """
    if turnover <= 0:
        return 0.0
    return max(turnover * buy_commission, min_commission)


def calc_sell_fees(
    turnover: float,
    *,
    sell_commission: float,
    stamp_duty: float,
    min_commission: float,
) -> tuple[float, float]:
    """
    拆分卖出费用。

    @param turnover: 成交额
    @returns: (卖出佣金, 印花税)
    """
    if turnover <= 0:
        return 0.0, 0.0
    commission = max(turnover * sell_commission, min_commission)
    stamp = turnover * stamp_duty
    return commission, stamp


def apply_slippage(
    price: float,
    side: Literal["buy", "sell"],
    *,
    slippage: float,
) -> float:
    """
    按比例滑点调整成交价（买贵卖贱）。

    @param price: 原始价
    @param side: buy/sell
    @param slippage: 滑点比例，如 0.001
    """
    if price <= 0 or slippage <= 0:
        return price
    if side == "buy":
        return price * (1.0 + slippage)
    return price * (1.0 - slippage)
