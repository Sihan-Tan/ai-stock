"""龙头首板简化版（迁移自 CASE-AI dragon_picker，单票日线适配）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="dragon_picker", name="龙头首板战法(单票)", version="v1.0")
class DragonPicker:
    """
    当日涨幅 + 量比 + 价位打分。

    回测默认用日线近似「今日」：涨幅=收/昨收，量比=量/近5日均量，高点=当日 high。
    若 ``ctx["history"]`` 含分钟级 date，则优先按当日分钟累计量与最高价。
    """

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        close = row.get("close")
        high = row.get("high")
        volume = row.get("volume")
        prev_close = row.get("prev_close")
        if None in (close, high, volume, prev_close) or prev_close <= 0:
            return []

        day_change = float(close) / float(prev_close) - 1.0
        today_high = float(high)
        today_vol = float(volume)
        avg_vol_5d = self._avg_vol_5d(ctx, float(volume))

        history = ctx.get("history") if isinstance(ctx, dict) else None
        if history is not None and not getattr(history, "empty", True) and "date" in history.columns:
            minute_stats = self._today_minute_stats(history)
            if minute_stats is not None:
                today_high, today_vol, close = minute_stats
                day_change = float(close) / float(prev_close) - 1.0

        vol_ratio = (today_vol / avg_vol_5d) if avg_vol_5d > 0 else 0.0
        drawdown = (float(close) / today_high - 1.0) if today_high > 0 else 0.0

        if day_change < -0.03 or drawdown < -0.03:
            return [
                Signal(
                    symbol=symbol,
                    side=Side.SELL,
                    reason=f"dragon_exit chg={day_change:+.2%} dd={drawdown:+.2%}",
                )
            ]

        score = 0.0
        if day_change > 0.09:
            score += 0.5
        else:
            score += min(max(day_change, 0) * 10, 1.0)
        score += min(vol_ratio / 3, 1.5)
        if close < 20:
            score += 0.5
        elif close <= 30:
            score += 0.2

        reason = (
            f"日涨={day_change:+.2%} 量比={vol_ratio:.2f} "
            f"价={float(close):.2f} 分={score:.2f}"
        )
        if day_change > 0.05 and vol_ratio > 2.0 and float(close) < 30 and score >= 1.5:
            return [Signal(symbol=symbol, side=Side.BUY, reason=reason)]
        return []

    @staticmethod
    def _avg_vol_5d(ctx, fallback: float) -> float:
        """近 5 日均量（不含当日）；不足则用当前量。"""
        history = ctx.get("history") if isinstance(ctx, dict) else None
        if history is None or getattr(history, "empty", True) or "volume" not in history.columns:
            return fallback
        vols = history["volume"].astype(float)
        if len(vols) < 6:
            return float(vols.iloc[:-1].mean()) if len(vols) > 1 else fallback
        return float(vols.iloc[-6:-1].mean())

    @staticmethod
    def _today_minute_stats(history) -> tuple[float, float, float] | None:
        """
        若历史为分钟级，取末日累计高/量与末收。

        @returns: (today_high, today_vol, last_close) 或 None
        """
        import pandas as pd

        ts = pd.to_datetime(history["date"])
        if len(ts) < 2:
            return None
        # 日线粒度跳过分钟路径
        deltas = ts.diff().dropna()
        if deltas.empty or deltas.median() >= pd.Timedelta(hours=12):
            return None
        today = ts.iloc[-1].normalize()
        mask = ts.dt.normalize() == today
        day = history.loc[mask]
        if day.empty:
            return None
        return (
            float(day["high"].max()),
            float(day["volume"].sum()),
            float(day["close"].iloc[-1]),
        )
