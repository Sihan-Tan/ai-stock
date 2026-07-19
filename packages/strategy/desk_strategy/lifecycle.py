"""
策略生命周期（参考 example/strategy/registry.py / CASE-24C）。

五阶段：incubating → paper → probation → production → retired
评估：按 KPI 自动决定是否晋级/退役，并建议资金占比。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LifecycleStage(str, Enum):
    """策略生命周期阶段。"""

    INCUBATING = "incubating"
    PAPER = "paper"
    PROBATION = "probation"
    PRODUCTION = "production"
    RETIRED = "retired"


STAGE_LABELS: dict[str, str] = {
    LifecycleStage.INCUBATING.value: "孵化",
    LifecycleStage.PAPER.value: "纸交易",
    LifecycleStage.PROBATION.value: "试用",
    LifecycleStage.PRODUCTION.value: "主力",
    LifecycleStage.RETIRED.value: "退役",
}

STAGE_ORDER = [
    LifecycleStage.INCUBATING,
    LifecycleStage.PAPER,
    LifecycleStage.PROBATION,
    LifecycleStage.PRODUCTION,
    LifecycleStage.RETIRED,
]


@dataclass
class StrategyKPI:
    """策略评估 KPI。"""

    rolling_30d_sharpe: float = 0.0
    rolling_30d_return: float = 0.0
    rolling_30d_maxdd: float = 0.0
    days_since_promotion: int = 0
    consecutive_low_sharpe_days: int = 0
    total_trades: int = 0
    win_rate: float = 0.0
    walk_forward_is_oos_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StrategyKPI:
        """反序列化，忽略未知字段。"""
        raw = data or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class MigrationResult:
    """单次阶段迁移结果。"""

    strategy_id: str
    from_stage: str
    to_stage: str
    reason: str
    capital_pct: float


def suggest_capital_pct(stage: LifecycleStage | str) -> float:
    """按阶段建议资金占比。"""
    st = LifecycleStage(stage)
    return {
        LifecycleStage.INCUBATING: 0.0,
        LifecycleStage.PAPER: 0.0,
        LifecycleStage.PROBATION: 0.05,
        LifecycleStage.PRODUCTION: 0.30,
        LifecycleStage.RETIRED: 0.0,
    }[st]


def decide_next_stage(stage: LifecycleStage | str, kpi: StrategyKPI) -> LifecycleStage | None:
    """
    根据 KPI 决定下一阶段；无变更则 None。

    规则摘自 CASE-24C：
    - 任意阶段：30 日最大回撤 > 20% → retired
    - incubating：IS/OOS ≥ 0.7 → paper
    - paper：晋升天数≥20 且 30 日收益>0 且回撤<5% → probation
    - probation：晋升天数≥20 且 Sharpe>0.5 → production
    - production：连续低 Sharpe ≥14 天 → retired
    """
    st = LifecycleStage(stage)

    # 强制退役仅针对试用/主力；孵化/纸交易的全样本回测回撤不应直接退役
    if st in (LifecycleStage.PROBATION, LifecycleStage.PRODUCTION) and kpi.rolling_30d_maxdd > 0.20:
        return LifecycleStage.RETIRED

    if st == LifecycleStage.INCUBATING:
        if kpi.walk_forward_is_oos_ratio >= 0.7:
            return LifecycleStage.PAPER
    elif st == LifecycleStage.PAPER:
        if (
            kpi.days_since_promotion >= 20
            and kpi.rolling_30d_return > 0
            and kpi.rolling_30d_maxdd < 0.05
        ):
            return LifecycleStage.PROBATION
    elif st == LifecycleStage.PROBATION:
        if kpi.days_since_promotion >= 20 and kpi.rolling_30d_sharpe > 0.5:
            return LifecycleStage.PRODUCTION
    elif st == LifecycleStage.PRODUCTION:
        if kpi.consecutive_low_sharpe_days >= 14:
            return LifecycleStage.RETIRED
    return None


def explain_migration(
    stage: LifecycleStage | str,
    new_stage: LifecycleStage,
    kpi: StrategyKPI,
) -> str:
    """生成迁移理由文案。"""
    old = LifecycleStage(stage)
    if new_stage == LifecycleStage.RETIRED:
        if kpi.rolling_30d_maxdd > 0.20:
            return f"30日最大回撤 {kpi.rolling_30d_maxdd:.1%} 超过 20%，强制退役"
        return f"连续 {kpi.consecutive_low_sharpe_days} 天 Sharpe 低于阈值"
    if new_stage == LifecycleStage.PAPER:
        return f"Walk-Forward IS/OOS 比例 {kpi.walk_forward_is_oos_ratio:.2f} ≥ 0.70，通过孵化"
    if new_stage == LifecycleStage.PROBATION:
        return (
            f"纸交易 {kpi.days_since_promotion} 天，"
            f"收益 {kpi.rolling_30d_return:+.2%}，回撤 {kpi.rolling_30d_maxdd:.2%}，通过试用门槛"
        )
    if new_stage == LifecycleStage.PRODUCTION:
        return f"试用期 Sharpe {kpi.rolling_30d_sharpe:.2f} > 0.5，升为主力"
    return f"{old.value} → {new_stage.value}"


def append_history(
    history: list[dict[str, Any]],
    *,
    from_stage: str | None,
    to_stage: str,
    reason: str,
) -> list[dict[str, Any]]:
    """追加阶段迁移历史。"""
    item = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "from": from_stage,
        "to": to_stage,
        "reason": reason,
    }
    return [*history, item]


def status_to_lifecycle(status: str) -> LifecycleStage:
    """将旧 status 映射为生命周期阶段（兼容已有数据）。"""
    mapping = {
        "draft": LifecycleStage.INCUBATING,
        "research": LifecycleStage.INCUBATING,
        "paper": LifecycleStage.PAPER,
        "live": LifecycleStage.PRODUCTION,
        "archived": LifecycleStage.RETIRED,
    }
    return mapping.get(status, LifecycleStage.INCUBATING)


def lifecycle_to_status(stage: LifecycleStage | str, *, current_status: str = "research") -> str:
    """
    生命周期写回 status。

    - draft 不因评估被覆盖
    - retired（生命周期退役）≠ archived（软删除），退役策略仍应出现在列表中
    """
    if current_status == "draft":
        return "draft"
    if current_status == "archived":
        # 软删除态保持，除非显式恢复
        return "archived"
    st = LifecycleStage(stage)
    mapping = {
        LifecycleStage.INCUBATING: "research",
        LifecycleStage.PAPER: "paper",
        LifecycleStage.PROBATION: "paper",
        LifecycleStage.PRODUCTION: "live",
        LifecycleStage.RETIRED: "research",
    }
    return mapping[st]


@dataclass
class ABTestResult:
    """A/B 评估结果。"""

    verdict: str
    winner: str | None = None
    loser: str | None = None
    winner_sharpe: float | None = None
    loser_sharpe: float | None = None
    msg: str = ""


def run_ab_evaluation(
    strategy_a: str,
    kpi_a: StrategyKPI,
    strategy_b: str,
    kpi_b: StrategyKPI,
    *,
    days_so_far: int = 30,
) -> ABTestResult:
    """比较两策略 30 日 Sharpe。"""
    if days_so_far < 20:
        return ABTestResult(verdict="not_enough_data", msg="样本不足 20 天")
    sa = kpi_a.rolling_30d_sharpe
    sb = kpi_b.rolling_30d_sharpe
    if abs(sa - sb) < 0.2:
        return ABTestResult(
            verdict="tie",
            msg=f"Sharpe 差距 {abs(sa - sb):.2f} 小于 0.2，不显著",
        )
    winner = strategy_a if sa > sb else strategy_b
    loser = strategy_b if winner == strategy_a else strategy_a
    return ABTestResult(
        verdict="decisive",
        winner=winner,
        loser=loser,
        winner_sharpe=max(sa, sb),
        loser_sharpe=min(sa, sb),
        msg=f"{winner} (Sharpe {max(sa, sb):.2f}) 胜出 vs {loser} (Sharpe {min(sa, sb):.2f})",
    )
