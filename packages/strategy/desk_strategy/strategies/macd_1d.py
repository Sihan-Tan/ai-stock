"""MACD 日线金叉/死叉（迁移自 CASE-AI macd_1d）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="macd_1d", name="MACD·日K线", version="v1.0")
class Macd1d:
    """DIF 上穿 DEA 买，下穿卖（12/26/9）。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        macd = row.get("macd")
        signal = row.get("macd_signal")
        prev_macd = row.get("prev_macd")
        prev_signal = row.get("prev_macd_signal")
        if None in (macd, signal, prev_macd, prev_signal):
            return []
        prev_diff = prev_macd - prev_signal
        curr_diff = macd - signal
        if prev_diff <= 0 and curr_diff > 0:
            return [Signal(symbol=symbol, side=Side.BUY, reason="macd_golden_cross")]
        if prev_diff >= 0 and curr_diff < 0:
            return [Signal(symbol=symbol, side=Side.SELL, reason="macd_death_cross")]
        return []
