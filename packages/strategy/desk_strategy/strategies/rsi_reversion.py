"""RSI 反转（迁移自 CASE-AI / walk_forward rsi_reversion）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="rsi_reversion", name="RSI反转", version="v1.0")
class RsiReversion:
    """RSI14 < 30 买，> 70 卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        rsi = row.get("rsi_14")
        if rsi is None:
            return []
        if rsi < 30:
            return [Signal(symbol=symbol, side=Side.BUY, reason="rsi_oversold")]
        if rsi > 70:
            return [Signal(symbol=symbol, side=Side.SELL, reason="rsi_overbought")]
        return []
