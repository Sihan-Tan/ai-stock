"""ML 概率因子（迁移自 CASE-AI ml_prob，精简特征+滚动重训）。"""

from __future__ import annotations

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy
from desk_strategy.ml_prob_engine import RollingProbState


@register_strategy(
    id="ml_prob",
    name="ML概率因子",
    version="v1.0",
    bar_period="1d",
)
class MlProb:
    """
    轻量价量/技术特征 + XGBoost/LightGBM 滚动训练。

    需 ``ctx["history"]`` 日线 DataFrame（回测已注入）；prob>0.60 买、<0.40 卖。
    """

    def __init__(self):
        self._state = RollingProbState(
            train_days=120,
            retrain_interval=20,
            horizon=1,
            model_type="xgboost",
        )
        self._buy_th = 0.60
        self._sell_th = 0.40

    def on_bar(self, ctx) -> list[Signal]:
        """生成信号。"""
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        history = ctx.get("history") if isinstance(ctx, dict) else None
        if history is None or getattr(history, "empty", True):
            return []
        if len(history) < 200:
            return []

        try:
            prob = self._state.predict_last(history)
        except Exception:  # noqa: BLE001
            return []

        if prob > self._buy_th:
            return [
                Signal(
                    symbol=symbol,
                    side=Side.BUY,
                    reason=f"ml_prob={prob:.2%} > 60%",
                )
            ]
        if prob < self._sell_th:
            return [
                Signal(
                    symbol=symbol,
                    side=Side.SELL,
                    reason=f"ml_prob={prob:.2%} < 40%",
                )
            ]
        return []
