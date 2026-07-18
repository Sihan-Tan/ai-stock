"""A 股回测费用：买卖佣金（可配）+ 卖出印花税 + 单笔最低佣金。"""

from __future__ import annotations

import backtrader as bt


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


class AShareCommission(bt.CommInfoBase):
    """
    A 股费用模型。

    - 买入：成交额 × 买入佣金率，不低于最低佣金
    - 卖出：成交额 ×（卖出佣金率 + 印花税），佣金部分不低于最低佣金；印花税按成交额另计
    """

    params = (
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
        ("percabs", True),
        ("buy_commission", 0.00025),
        ("sell_commission", 0.00025),
        ("stamp_duty", 0.001),
        ("min_commission", 5.0),
    )

    def _getcommission(self, size, price, pseudoexec):
        """
        计算单笔费用。

        @param size: 正=买入，负=卖出
        @param price: 成交价
        @param pseudoexec: backtrader 预估标记
        @returns: 费用金额（元）
        """
        turnover = abs(size) * price
        if turnover <= 0:
            return 0.0
        if size > 0:
            return calc_buy_commission(
                turnover,
                buy_commission=float(self.p.buy_commission),
                min_commission=float(self.p.min_commission),
            )
        exit_comm, stamp = calc_sell_fees(
            turnover,
            sell_commission=float(self.p.sell_commission),
            stamp_duty=float(self.p.stamp_duty),
            min_commission=float(self.p.min_commission),
        )
        return exit_comm + stamp
