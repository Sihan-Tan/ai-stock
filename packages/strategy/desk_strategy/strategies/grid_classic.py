"""经典网格（迁移自 CASE-AI grid_classic，日线无状态版）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="grid_classic", name="经典网格60日", version="v1.0")
class GridClassic:
    """60 日高低切 8 格：底部 2 格买，顶部 2 格卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        close = row.get("close")
        high_60 = row.get("range_high_60")
        low_60 = row.get("range_low_60")
        if None in (close, high_60, low_60) or high_60 <= low_60:
            return []
        margin = (high_60 - low_60) * 0.02
        upper = high_60 + margin
        lower = low_60 - margin
        grid_size = (upper - lower) / 8
        if grid_size <= 0:
            return []
        if close < lower:
            return [Signal(symbol=symbol, side=Side.SELL, reason="grid_stop_loss")]
        if close > upper:
            return [Signal(symbol=symbol, side=Side.SELL, reason="grid_take_profit")]
        grid_idx = int((close - lower) / grid_size)
        grid_idx = max(0, min(7, grid_idx))
        if grid_idx <= 1:
            return [Signal(symbol=symbol, side=Side.BUY, reason="grid_bottom")]
        if grid_idx >= 6:
            return [Signal(symbol=symbol, side=Side.SELL, reason="grid_top")]
        return []
