"""5 分钟双均线 EMA5/EMA20（迁移自 CASE-AI dual_ma_5min）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(
    id="dual_ma_5min",
    name="双均线 5min (5/20 EMA)",
    version="v1.0",
    bar_period="5m",
)
class DualMa5min:
    """5EMA 上穿 20EMA 买，下穿卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        fast = row.get("ema_5")
        slow = row.get("ema_20")
        prev_fast = row.get("prev_ema_5")
        prev_slow = row.get("prev_ema_20")
        if None in (fast, slow, prev_fast, prev_slow):
            return []
        if prev_fast <= prev_slow and fast > slow:
            return [Signal(symbol=symbol, side=Side.BUY, reason="ema5_cross_up_20")]
        if prev_fast >= prev_slow and fast < slow:
            return [Signal(symbol=symbol, side=Side.SELL, reason="ema5_cross_down_20")]
        return []
