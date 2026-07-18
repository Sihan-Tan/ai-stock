"""乖离率均值回归（迁移自 CASE-AI bias_revert）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="bias_revert", name="乖离率均值回归", version="v1.0")
class BiasRevert:
    """BIAS20 < -6% 买，> 3% 卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        bias = row.get("bias_20")
        if bias is None:
            return []
        if bias < -0.06:
            return [Signal(symbol=symbol, side=Side.BUY, reason="bias_oversold")]
        if bias > 0.03:
            return [Signal(symbol=symbol, side=Side.SELL, reason="bias_overbought")]
        return []
