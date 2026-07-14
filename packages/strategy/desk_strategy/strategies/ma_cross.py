"""双均线示例策略（Python 注册）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="ma_cross", name="双均线-日线", version="v1.0")
class MaCross:
    """简单双均线：sma5 上穿 sma20 买入。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        fast = row.get("sma_5")
        slow = row.get("sma_20")
        prev_fast = row.get("prev_sma_5")
        prev_slow = row.get("prev_sma_20")
        if None in (fast, slow, prev_fast, prev_slow):
            return []
        if prev_fast <= prev_slow and fast > slow:
            return [Signal(symbol=symbol, side=Side.BUY, reason="ma_golden_cross")]
        if prev_fast >= prev_slow and fast < slow:
            return [Signal(symbol=symbol, side=Side.SELL, reason="ma_death_cross")]
        return []
