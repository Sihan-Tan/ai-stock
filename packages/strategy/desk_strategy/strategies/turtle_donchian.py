"""海龟唐奇安通道（迁移自 CASE-AI turtle_donchian）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="turtle_donchian", name="海龟唐奇安通道", version="v1.0")
class TurtleDonchian:
    """突破 20 日高买，跌破 10 日低卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        close = row.get("close")
        entry_high = row.get("donchian_entry_high_20")
        exit_low = row.get("donchian_exit_low_10")
        if None in (close, entry_high, exit_low):
            return []
        if close > entry_high:
            return [Signal(symbol=symbol, side=Side.BUY, reason="donchian_breakout")]
        if close < exit_low:
            return [Signal(symbol=symbol, side=Side.SELL, reason="donchian_breakdown")]
        return []
