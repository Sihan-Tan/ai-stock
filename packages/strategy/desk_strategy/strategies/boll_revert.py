"""布林带均值回归（迁移自 CASE-AI boll_revert）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="boll_revert", name="布林带均值回归", version="v1.0")
class BollRevert:
    """触下轨买；触上轨或跌破中轨卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        close = row.get("close")
        prev_close = row.get("prev_close")
        mid = row.get("boll_mid")
        upper = row.get("boll_upper")
        lower = row.get("boll_lower")
        prev_mid = row.get("prev_boll_mid")
        if None in (close, prev_close, mid, upper, lower, prev_mid):
            return []
        if close < lower:
            return [Signal(symbol=symbol, side=Side.BUY, reason="touch_boll_lower")]
        if close > upper:
            return [Signal(symbol=symbol, side=Side.SELL, reason="touch_boll_upper")]
        if prev_close >= prev_mid and close < mid:
            return [Signal(symbol=symbol, side=Side.SELL, reason="break_boll_mid")]
        return []
