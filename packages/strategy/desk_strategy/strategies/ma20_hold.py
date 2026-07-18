"""MA20 持股法（迁移自 CASE-AI ma20_hold）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="ma20_hold", name="MA20持股法", version="v1.0")
class Ma20Hold:
    """收盘上穿 MA20 买，下穿卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        close = row.get("close")
        prev_close = row.get("prev_close")
        sma_20 = row.get("sma_20")
        prev_sma_20 = row.get("prev_sma_20")
        if None in (close, prev_close, sma_20, prev_sma_20):
            return []
        if prev_close <= prev_sma_20 and close > sma_20:
            return [Signal(symbol=symbol, side=Side.BUY, reason="close_break_ma20")]
        if prev_close >= prev_sma_20 and close < sma_20:
            return [Signal(symbol=symbol, side=Side.SELL, reason="close_lose_ma20")]
        return []
