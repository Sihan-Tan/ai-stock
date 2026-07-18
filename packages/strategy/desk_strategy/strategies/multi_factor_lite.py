"""多因子轻量版（迁移自 CASE-AI multi_factor_top 绝对阈值版）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="multi_factor_lite", name="多因子轻量", version="v1.0")
class MultiFactorLite:
    """MOM_1M + RSI + BIAS 合成 alpha，>0.3 买，<-0.3 卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        mom_1m = row.get("mom_1m")
        rsi = row.get("rsi_14")
        bias = row.get("bias_20")
        if None in (mom_1m, rsi, bias):
            return []

        f_mom = max(-1.0, min(1.0, float(mom_1m) / 0.15))
        if rsi > 70:
            f_rsi = -((rsi - 70) / 30)
        elif rsi < 30:
            f_rsi = (30 - rsi) / 30
        else:
            f_rsi = (rsi - 50) / 50
        f_bias = max(-1.0, min(1.0, -float(bias) / 0.10))
        alpha = (f_mom + f_rsi + f_bias) / 3.0

        if alpha > 0.30:
            return [Signal(symbol=symbol, side=Side.BUY, reason=f"alpha={alpha:+.2f}")]
        if alpha < -0.30:
            return [Signal(symbol=symbol, side=Side.SELL, reason=f"alpha={alpha:+.2f}")]
        return []
