"""策略管理：清单、YAML、生命周期与 KPI 评估。"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_strategy import STAGE_LABELS, StrategyRegistry
from desk_strategy.lifecycle import LifecycleStage

router = APIRouter(prefix="/strategies")


class YamlIn(BaseModel):
    yaml_body: str


class DraftIn(BaseModel):
    payload: dict


class StageIn(BaseModel):
    stage: str
    reason: str = "手动调整阶段"


class KpiIn(BaseModel):
    rolling_30d_sharpe: float | None = None
    rolling_30d_return: float | None = None
    rolling_30d_maxdd: float | None = None
    days_since_promotion: int | None = None
    consecutive_low_sharpe_days: int | None = None
    total_trades: int | None = None
    win_rate: float | None = None
    walk_forward_is_oos_ratio: float | None = None


class AbIn(BaseModel):
    strategy_a: str
    strategy_b: str
    days_so_far: int = Field(30, ge=1, le=365)


@router.get("")
def list_strategies(
    source: str | None = None,
    include_archived: bool = Query(False, description="是否包含软删除策略"),
    db: Session = Depends(get_db),
):
    return [
        m.model_dump()
        for m in StrategyRegistry(db).list(source, include_archived=include_archived)
    ]


@router.get("/lifecycle/summary")
def lifecycle_summary(db: Session = Depends(get_db)):
    """生命周期阶段汇总与资金占用。"""
    return StrategyRegistry(db).lifecycle_summary()


@router.get("/lifecycle/stages")
def lifecycle_stages():
    """阶段枚举与中文标签。"""
    return {
        "stages": [s.value for s in LifecycleStage],
        "labels": STAGE_LABELS,
    }


@router.post("/lifecycle/evaluate")
def lifecycle_evaluate(
    refresh_from_backtest: bool = Query(True),
    db: Session = Depends(get_db),
):
    """按 KPI 自动评估并迁移阶段。"""
    migrations = StrategyRegistry(db).evaluate_and_migrate(
        refresh_from_backtest=refresh_from_backtest
    )
    summary = StrategyRegistry(db).lifecycle_summary()
    return {"migrations": migrations, "summary": summary}


@router.post("/lifecycle/restore")
def lifecycle_restore(db: Session = Depends(get_db)):
    """恢复误归档/隐藏的策略，重新出现在列表中。"""
    n = StrategyRegistry(db).restore_visible_strategies()
    return {"restored": n, "summary": StrategyRegistry(db).lifecycle_summary()}


@router.post("/lifecycle/ab-test")
def lifecycle_ab_test(body: AbIn, db: Session = Depends(get_db)):
    """两策略 A/B 评估。"""
    try:
        return StrategyRegistry(db).ab_evaluate(
            body.strategy_a, body.strategy_b, days_so_far=body.days_so_far
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/sync-python")
def sync_python(db: Session = Depends(get_db)):
    n = StrategyRegistry(db).sync_python_to_db()
    return {"synced": n}


@router.post("/from-yaml")
def from_yaml(body: YamlIn, db: Session = Depends(get_db)):
    """保存 YAML 策略；阶段重置为孵化。"""
    meta = StrategyRegistry(db).from_yaml(body.yaml_body, reset_lifecycle=True)
    return meta.model_dump()


@router.post("/load-yaml-file")
def load_file(db: Session = Depends(get_db)):
    candidates = [
        Path("configs/strategies/breakout.yaml"),
        Path(__file__).resolve().parents[4] / "configs" / "strategies" / "breakout.yaml",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        raise HTTPException(404, "yaml not found")
    return StrategyRegistry(db).load_yaml_file(path).model_dump()


@router.post("/draft")
def draft(body: DraftIn, db: Session = Depends(get_db)):
    return StrategyRegistry(db).save_agent_draft(body.payload).model_dump()


@router.get("/{strategy_id}")
def get_strategy(strategy_id: str, db: Session = Depends(get_db)):
    """按 ID 取策略元数据（含 yaml_body 与生命周期历史）。"""
    meta = StrategyRegistry(db).get_meta(strategy_id)
    if not meta:
        # 尝试同步后再取（Python 策略可能尚未落库）
        StrategyRegistry(db).sync_python_to_db()
        meta = StrategyRegistry(db).get_meta(strategy_id)
    if not meta:
        raise HTTPException(404, "not found")
    return meta.model_dump()


@router.get("/{strategy_id}/source")
def get_strategy_source(strategy_id: str, db: Session = Depends(get_db)):
    """取策略可编辑源码（YAML 正文或 Python 类源码）。"""
    payload = StrategyRegistry(db).get_source_text(strategy_id)
    if not payload:
        raise HTTPException(404, "not found")
    return payload


@router.post("/{strategy_id}/promote")
def promote(strategy_id: str, db: Session = Depends(get_db)):
    meta = StrategyRegistry(db).promote(strategy_id)
    if not meta:
        raise HTTPException(404, "not found")
    return meta.model_dump()


@router.post("/{strategy_id}/lifecycle/stage")
def set_lifecycle_stage(strategy_id: str, body: StageIn, db: Session = Depends(get_db)):
    """手动设置生命周期阶段。"""
    try:
        LifecycleStage(body.stage)
    except ValueError as exc:
        raise HTTPException(400, f"invalid stage: {body.stage}") from exc
    meta = StrategyRegistry(db).set_stage(strategy_id, body.stage, reason=body.reason)
    if not meta:
        raise HTTPException(404, "not found")
    return meta.model_dump()


@router.post("/{strategy_id}/lifecycle/kpi")
def update_lifecycle_kpi(strategy_id: str, body: KpiIn, db: Session = Depends(get_db)):
    """更新策略 KPI。"""
    payload: dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(400, "no kpi fields")
    meta = StrategyRegistry(db).update_kpi(strategy_id, **payload)
    if not meta:
        raise HTTPException(404, "not found")
    return meta.model_dump()


class WalkForwardIn(BaseModel):
    """Walk-Forward 请求。"""

    symbol: str | None = None


@router.post("/{strategy_id}/lifecycle/walk-forward")
def lifecycle_walk_forward(
    strategy_id: str,
    body: WalkForwardIn | None = None,
    db: Session = Depends(get_db),
):
    """跑 Walk-Forward 并写入 KPI 的 IS/OOS 比例。"""
    payload = body or WalkForwardIn()
    result = StrategyRegistry(db).apply_walk_forward(
        strategy_id, symbol=payload.symbol
    )
    if result.get("status") == "error" and "not found" in str(result.get("message", "")):
        raise HTTPException(404, result.get("message") or "not found")
    return result


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: str, db: Session = Depends(get_db)):
    """
    删除策略：未软删 → 软删除（archived / retired）；已软删 → 硬删除。
    """
    result = StrategyRegistry(db).delete(strategy_id)
    if not result:
        raise HTTPException(404, "not found")
    return result
