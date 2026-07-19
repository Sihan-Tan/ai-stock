"""生命周期晋升闸门：未达试用/主力则禁止买入。"""

from __future__ import annotations

from desk_strategy.lifecycle import LifecycleStage, suggest_capital_pct

# 允许开新仓的阶段
BUY_ALLOWED_STAGES = frozenset(
    {
        LifecycleStage.PROBATION.value,
        LifecycleStage.PRODUCTION.value,
    }
)


def can_buy(stage: str | None) -> bool:
    """
    当前阶段是否允许买入开仓。

    @param stage: lifecycle_stage
    """
    return (stage or "") in BUY_ALLOWED_STAGES


def buy_block_reason(stage: str | None) -> str | None:
    """
    若不可买入返回原因，否则 None。

    @param stage: lifecycle_stage
    """
    if can_buy(stage):
        return None
    label = stage or "unknown"
    return f"lifecycle gate: stage={label} cannot buy (need probation/production)"


def max_capital_pct(stage: str | None) -> float:
    """
    阶段建议最大资金占比。

    @param stage: lifecycle_stage
    """
    if not stage:
        return 0.0
    try:
        return float(suggest_capital_pct(stage))
    except ValueError:
        return 0.0
