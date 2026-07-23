"""策略注册、YAML / Agent 草稿与生命周期管理。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.contracts import Side, Signal, StrategyMeta, StrategySource
from desk_common.settings import get_settings
from desk_db.models import BacktestRun, StrategyRow
from desk_strategy.lifecycle import (
    ABTestResult,
    LifecycleStage,
    MigrationResult,
    STAGE_LABELS,
    StrategyKPI,
    append_history,
    decide_next_stage,
    explain_migration,
    lifecycle_to_status,
    run_ab_evaluation,
    status_to_lifecycle,
    suggest_capital_pct,
)

_REGISTRY: dict[str, "RegisteredStrategy"] = {}

__all__ = [
    "LifecycleStage",
    "RegisteredStrategy",
    "STAGE_LABELS",
    "StrategyKPI",
    "StrategyRegistry",
    "register_strategy",
]


@dataclass
class RegisteredStrategy:
    """内存中的可执行策略。"""

    meta: StrategyMeta
    on_bar: Callable[[Any], list[Signal]] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def register_strategy(
    id: str,
    name: str | None = None,
    version: str = "v0.1",
    **params: Any,
):
    """
    Python 策略装饰器注册。

    @param id: 策略 ID
    """

    def deco(cls_or_fn):
        # 类策略单例缓存：ml_prob 等有状态策略需跨 bar 复用实例
        holder: dict[str, Any] = {"inst": None}

        def _on_bar(ctx):
            if hasattr(cls_or_fn, "on_bar"):
                if holder["inst"] is None:
                    holder["inst"] = (
                        cls_or_fn() if isinstance(cls_or_fn, type) else cls_or_fn
                    )
                return holder["inst"].on_bar(ctx)
            return cls_or_fn(ctx)

        meta = StrategyMeta(
            id=id,
            name=name or id,
            source=StrategySource.PYTHON,
            version=version,
            status="research",
            entry_point=f"{getattr(cls_or_fn, '__module__', '')}:{getattr(cls_or_fn, '__name__', id)}",
            params=params,
        )
        _REGISTRY[id] = RegisteredStrategy(meta=meta, on_bar=_on_bar)
        return cls_or_fn

    return deco


class StrategyRegistry:
    """策略注册表（Python / YAML / Agent）。"""

    def __init__(self, db: Session):
        self.db = db

    def sync_python_to_db(self) -> int:
        """将装饰器注册写入 DB。"""
        # 触发子包策略导入（含 CASE-AI 迁移策略）
        import desk_strategy.strategies  # noqa: F401

        n = 0
        for sid, reg in _REGISTRY.items():
            existing = self.db.scalar(
                select(StrategyRow).where(
                    StrategyRow.strategy_id == sid, StrategyRow.version == reg.meta.version
                )
            )
            if existing:
                # 名称/入口保持最新；不自动撤销软删除（恢复请走 restore）
                existing.name = reg.meta.name
                existing.entry_point = reg.meta.entry_point
                self._ensure_lifecycle_defaults(existing)
                continue
            stage = status_to_lifecycle(reg.meta.status)
            hist = append_history([], from_stage=None, to_stage=stage.value, reason="Python 同步注册")
            self.db.add(
                StrategyRow(
                    strategy_id=sid,
                    name=reg.meta.name,
                    source="python",
                    version=reg.meta.version,
                    status=reg.meta.status,
                    lifecycle_stage=stage.value,
                    capital_pct=suggest_capital_pct(stage),
                    capital_allocated=0.0,
                    kpi_json="{}",
                    lifecycle_history_json=json.dumps(hist, ensure_ascii=False),
                    entry_point=reg.meta.entry_point,
                    params_json=json.dumps(reg.meta.params, ensure_ascii=False),
                    lifecycle_updated_at=datetime.utcnow(),
                )
            )
            n += 1
        self.db.flush()
        return n

    def from_yaml(
        self,
        doc: str | dict[str, Any],
        status: str = "research",
        *,
        reset_lifecycle: bool = False,
    ) -> StrategyMeta:
        """
        解析 YAML 并入库。

        @param reset_lifecycle: 为 True 时（UI 新增/编辑保存）阶段重置为孵化并记历史
        """
        data = yaml.safe_load(doc) if isinstance(doc, str) else doc
        sid = str(data["id"])
        meta = StrategyMeta(
            id=sid,
            name=data.get("name", sid),
            source=StrategySource.YAML,
            version=str(data.get("version", "v0.1")),
            status=status,  # type: ignore[arg-type]
            lifecycle_stage="incubating",
            yaml_body=yaml.safe_dump(data, allow_unicode=True),
            params=data.get("params") or {},
        )
        self._upsert_row(meta, reset_lifecycle=reset_lifecycle)
        _REGISTRY[sid] = RegisteredStrategy(
            meta=meta,
            on_bar=lambda ctx, d=data: self._yaml_on_bar(d, ctx),
        )
        return self.get_meta(sid) or meta

    def save_agent_draft(self, payload: dict[str, Any]) -> StrategyMeta:
        """Agent 草稿（默认 draft）；保存后阶段重置为孵化。"""
        body = payload.get("yaml_body") or payload
        if isinstance(body, str):
            data = yaml.safe_load(body)
        else:
            data = dict(body)
        data["id"] = data.get("id") or payload.get("id") or "agent_draft"
        meta = self.from_yaml(data, status="draft", reset_lifecycle=True)
        row = self._latest_row(meta.id)
        if row:
            row.source = "agent"
            row.status = "draft"
            self.db.flush()
        meta.source = StrategySource.AGENT
        return self.get_meta(meta.id) or meta

    def promote(self, strategy_id: str, to_status: str = "research") -> StrategyMeta | None:
        """草稿晋级为 research，并进入孵化阶段。"""
        row = self._latest_row(strategy_id)
        if not row:
            return None
        row.status = to_status
        if to_status != "draft":
            self._apply_stage(
                row,
                LifecycleStage.INCUBATING,
                reason="草稿晋级进入孵化",
                reset_promotion_days=True,
            )
        self.db.flush()
        if strategy_id in _REGISTRY:
            _REGISTRY[strategy_id].meta.status = to_status  # type: ignore[assignment]
            _REGISTRY[strategy_id].meta.lifecycle_stage = row.lifecycle_stage  # type: ignore[assignment]
        return self._row_to_meta(row)

    def delete(self, strategy_id: str) -> dict[str, Any] | None:
        """
        删除策略：首次软删除（status=archived），已软删则硬删除行。

        @param strategy_id: 策略 ID
        @returns: ``{"action": "soft"|"hard", "strategy_id": ...}``；不存在则 None
        """
        rows = list(
            self.db.scalars(
                select(StrategyRow).where(StrategyRow.strategy_id == strategy_id)
            ).all()
        )
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.id)
        if latest.status != "archived":
            for row in rows:
                self._ensure_lifecycle_defaults(row)
                row.status = "archived"
                self._apply_stage(
                    row,
                    LifecycleStage.RETIRED,
                    reason="软删除退役",
                    reset_promotion_days=True,
                )
            self.db.flush()
            if strategy_id in _REGISTRY:
                _REGISTRY[strategy_id].meta.status = "archived"
                _REGISTRY[strategy_id].meta.lifecycle_stage = "retired"
            return {"action": "soft", "strategy_id": strategy_id}

        for row in rows:
            self.db.delete(row)
        self.db.flush()
        _REGISTRY.pop(strategy_id, None)
        return {"action": "hard", "strategy_id": strategy_id}

    def list(
        self, source: str | None = None, *, include_archived: bool = False
    ) -> list[StrategyMeta]:
        """
        列出策略。

        @param source: 可选来源过滤
        @param include_archived: 是否包含软删除（archived）
        """
        self.sync_python_to_db()
        q = select(StrategyRow).order_by(StrategyRow.id.desc())
        if source:
            q = q.where(StrategyRow.source == source)
        if not include_archived:
            q = q.where(StrategyRow.status != "archived")
        rows = self.db.scalars(q).all()
        out: list[StrategyMeta] = []
        for r in rows:
            self._ensure_lifecycle_defaults(r)
            out.append(self._row_to_meta(r))
        self.db.flush()
        return out

    def load(self, strategy_id: str) -> RegisteredStrategy | None:
        """加载可执行策略。"""
        self.sync_python_to_db()
        if strategy_id in _REGISTRY:
            return _REGISTRY[strategy_id]
        row = self.db.scalar(
            select(StrategyRow)
            .where(StrategyRow.strategy_id == strategy_id)
            .order_by(StrategyRow.id.desc())
        )
        if not row:
            return None
        if row.yaml_body:
            return _REGISTRY.get(strategy_id) or (
                self.from_yaml(row.yaml_body, status=row.status)
                and _REGISTRY.get(strategy_id)
            )
        return None

    def load_yaml_file(self, path: str | Path) -> StrategyMeta:
        """从文件加载 YAML。"""
        text = Path(path).read_text(encoding="utf-8")
        return self.from_yaml(text)

    def get_meta(self, strategy_id: str) -> StrategyMeta | None:
        """按 ID 取最新策略元数据。"""
        row = self._latest_row(strategy_id)
        if not row:
            return None
        self._ensure_lifecycle_defaults(row)
        return self._row_to_meta(row)

    def get_source_text(self, strategy_id: str) -> dict[str, Any] | None:
        """
        取可编辑源码：YAML/Agent 用 yaml_body；Python 用 inspect 读类源码。

        @returns: {strategy_id, source, language, text} 或 None
        """
        import inspect

        self.sync_python_to_db()
        meta = self.get_meta(strategy_id)
        if not meta:
            return None
        src = meta.source.value if hasattr(meta.source, "value") else str(meta.source)
        if src != "python":
            return {
                "strategy_id": strategy_id,
                "source": src,
                "language": "yaml",
                "text": meta.yaml_body or "",
            }
        text = ""
        ep = meta.entry_point or ""
        if ":" in ep:
            mod_name, qual = ep.split(":", 1)
            try:
                import importlib

                mod = importlib.import_module(mod_name)
                obj = getattr(mod, qual, None)
                if obj is not None:
                    text = inspect.getsource(obj)
            except Exception:  # noqa: BLE001
                text = ""
        if not text:
            text = (
                f"# Python 策略 {strategy_id}\n"
                f"# entry_point: {meta.entry_point or 'unknown'}\n"
                "# 未能读取源码；请在 packages/strategy 中打开对应文件。\n"
            )
        return {
            "strategy_id": strategy_id,
            "source": "python",
            "language": "python",
            "text": text,
        }

    def _upsert_row(self, meta: StrategyMeta, *, reset_lifecycle: bool = False) -> None:
        existing = self.db.scalar(
            select(StrategyRow).where(
                StrategyRow.strategy_id == meta.id, StrategyRow.version == meta.version
            )
        )
        stage = LifecycleStage(meta.lifecycle_stage or status_to_lifecycle(meta.status).value)
        if existing:
            existing.name = meta.name
            existing.source = meta.source.value
            existing.status = meta.status
            existing.yaml_body = meta.yaml_body
            existing.entry_point = meta.entry_point
            existing.params_json = json.dumps(meta.params, ensure_ascii=False)
            if meta.description:
                existing.description = meta.description
            self._ensure_lifecycle_defaults(existing)
            if reset_lifecycle:
                self._apply_stage(
                    existing,
                    LifecycleStage.INCUBATING,
                    reason="编辑保存，重置为孵化",
                    reset_promotion_days=True,
                )
                # 草稿 status 不被 _apply_stage 覆盖；YAML 成品保持 research
                if meta.status == "draft":
                    existing.status = "draft"
                elif existing.status != "archived":
                    existing.status = meta.status
        else:
            hist = append_history(
                [], from_stage=None, to_stage=stage.value, reason="新建策略"
            )
            self.db.add(
                StrategyRow(
                    strategy_id=meta.id,
                    name=meta.name,
                    source=meta.source.value,
                    version=meta.version,
                    status=meta.status,
                    lifecycle_stage=stage.value,
                    description=meta.description or "",
                    capital_pct=suggest_capital_pct(stage),
                    capital_allocated=0.0,
                    kpi_json=json.dumps(meta.kpi or {}, ensure_ascii=False),
                    lifecycle_history_json=json.dumps(hist, ensure_ascii=False),
                    entry_point=meta.entry_point,
                    yaml_body=meta.yaml_body,
                    params_json=json.dumps(meta.params, ensure_ascii=False),
                    lifecycle_updated_at=datetime.utcnow(),
                )
            )
        self.db.flush()

    def update_kpi(self, strategy_id: str, **kpi_kwargs: Any) -> StrategyMeta | None:
        """更新策略 KPI 字段。"""
        row = self._latest_row(strategy_id)
        if not row:
            return None
        self._ensure_lifecycle_defaults(row)
        kpi = StrategyKPI.from_dict(json.loads(row.kpi_json or "{}"))
        for key, value in kpi_kwargs.items():
            if hasattr(kpi, key):
                setattr(kpi, key, value)
        row.kpi_json = json.dumps(kpi.to_dict(), ensure_ascii=False)
        row.lifecycle_updated_at = datetime.utcnow()
        self.db.flush()
        return self._row_to_meta(row)

    def apply_walk_forward(
        self,
        strategy_id: str,
        *,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """
        跑 Walk-Forward 并将 ``walk_forward_is_oos_ratio`` 写入 KPI。

        @param strategy_id: 策略 ID
        @param symbol: 标的；缺省用最近回测标的
        """
        from desk_backtest.walk_forward import run_walk_forward

        row = self._latest_row(strategy_id)
        if not row:
            return {"status": "error", "message": "strategy not found", "strategy_id": strategy_id}
        self._ensure_lifecycle_defaults(row)
        sym = symbol
        if not sym:
            run = self.db.scalar(
                select(BacktestRun)
                .where(BacktestRun.strategy_id == strategy_id)
                .order_by(BacktestRun.id.desc())
            )
            sym = run.symbol if run else None
        if not sym:
            return {
                "status": "error",
                "strategy_id": strategy_id,
                "message": "symbol required (or run a backtest first)",
                "walk_forward_is_oos_ratio": 0.0,
            }
        result = run_walk_forward(self.db, strategy_id=strategy_id, symbol=sym)
        if result.get("status") == "ok":
            kpi = StrategyKPI.from_dict(json.loads(row.kpi_json or "{}"))
            kpi.walk_forward_is_oos_ratio = float(result["walk_forward_is_oos_ratio"])
            if result.get("oos_return") is not None and not kpi.rolling_30d_return:
                kpi.rolling_30d_return = float(result["oos_return"])
            if result.get("oos_sharpe") is not None and not kpi.rolling_30d_sharpe:
                kpi.rolling_30d_sharpe = float(result["oos_sharpe"] or 0)
            row.kpi_json = json.dumps(kpi.to_dict(), ensure_ascii=False)
            row.lifecycle_updated_at = datetime.utcnow()
            self.db.flush()
            result["kpi"] = kpi.to_dict()
        return result

    def set_stage(
        self,
        strategy_id: str,
        stage: str,
        *,
        reason: str = "手动调整阶段",
    ) -> StrategyMeta | None:
        """手动设置生命周期阶段。"""
        row = self._latest_row(strategy_id)
        if not row:
            return None
        self._ensure_lifecycle_defaults(row)
        new_stage = LifecycleStage(stage)
        self._apply_stage(row, new_stage, reason=reason, reset_promotion_days=True)
        self.db.flush()
        return self._row_to_meta(row)

    def evaluate_and_migrate(
        self, *, refresh_from_backtest: bool = True
    ) -> list[dict[str, Any]]:
        """
        按 KPI 评估全部策略并自动迁移阶段。

        @param refresh_from_backtest: 评估前用最近回测报告填充空 KPI
        """
        self.sync_python_to_db()
        rows = list(self.db.scalars(select(StrategyRow)).all())
        migrations: list[MigrationResult] = []
        for row in rows:
            if row.status == "archived" and row.lifecycle_stage == LifecycleStage.RETIRED.value:
                continue
            self._ensure_lifecycle_defaults(row)
            if refresh_from_backtest:
                self._refresh_kpi_from_backtest(row)
                # 孵化阶段且尚无 WF 比例时，用最近回测标的自动补算
                kpi0 = StrategyKPI.from_dict(json.loads(row.kpi_json or "{}"))
                if (
                    row.lifecycle_stage == LifecycleStage.INCUBATING.value
                    and float(kpi0.walk_forward_is_oos_ratio or 0) <= 0
                ):
                    self.apply_walk_forward(row.strategy_id)
            kpi = StrategyKPI.from_dict(json.loads(row.kpi_json or "{}"))
            # 已在生产且低 Sharpe 时累加连续天数（简化：每次评估 +1 若 sharpe<0.3）
            if (
                row.lifecycle_stage == LifecycleStage.PRODUCTION.value
                and kpi.rolling_30d_sharpe < 0.3
            ):
                kpi.consecutive_low_sharpe_days = int(kpi.consecutive_low_sharpe_days) + 1
                row.kpi_json = json.dumps(kpi.to_dict(), ensure_ascii=False)
            elif row.lifecycle_stage == LifecycleStage.PRODUCTION.value:
                kpi.consecutive_low_sharpe_days = 0
                row.kpi_json = json.dumps(kpi.to_dict(), ensure_ascii=False)

            next_stage = decide_next_stage(row.lifecycle_stage, kpi)
            if not next_stage or next_stage.value == row.lifecycle_stage:
                # 未迁移时也推进晋升计天数（简化：每次评估 +1）
                if row.lifecycle_stage not in (
                    LifecycleStage.RETIRED.value,
                    LifecycleStage.PRODUCTION.value,
                ):
                    kpi.days_since_promotion = int(kpi.days_since_promotion) + 1
                    row.kpi_json = json.dumps(kpi.to_dict(), ensure_ascii=False)
                continue
            reason = explain_migration(row.lifecycle_stage, next_stage, kpi)
            old = row.lifecycle_stage
            self._apply_stage(row, next_stage, reason=reason, reset_promotion_days=True)
            migrations.append(
                MigrationResult(
                    strategy_id=row.strategy_id,
                    from_stage=old,
                    to_stage=next_stage.value,
                    reason=reason,
                    capital_pct=row.capital_pct,
                )
            )
        self.db.flush()
        return [
            {
                "strategy_id": m.strategy_id,
                "from": m.from_stage,
                "to": m.to_stage,
                "reason": m.reason,
                "capital_pct": m.capital_pct,
            }
            for m in migrations
        ]

    def ab_evaluate(
        self, strategy_a: str, strategy_b: str, *, days_so_far: int = 30
    ) -> dict[str, Any]:
        """两策略 A/B Sharpe 评估。"""
        ra = self._latest_row(strategy_a)
        rb = self._latest_row(strategy_b)
        if not ra or not rb:
            raise KeyError("strategy not found")
        self._ensure_lifecycle_defaults(ra)
        self._ensure_lifecycle_defaults(rb)
        result: ABTestResult = run_ab_evaluation(
            strategy_a,
            StrategyKPI.from_dict(json.loads(ra.kpi_json or "{}")),
            strategy_b,
            StrategyKPI.from_dict(json.loads(rb.kpi_json or "{}")),
            days_so_far=days_so_far,
        )
        return {
            "verdict": result.verdict,
            "winner": result.winner,
            "loser": result.loser,
            "winner_sharpe": result.winner_sharpe,
            "loser_sharpe": result.loser_sharpe,
            "msg": result.msg,
        }

    def lifecycle_summary(self) -> dict[str, Any]:
        """按阶段汇总策略与资金占用。"""
        total = float(get_settings().paper_initial_cash)
        rows = list(self.db.scalars(select(StrategyRow)).all())
        by_stage: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            self._ensure_lifecycle_defaults(row)
            meta = self._row_to_meta(row)
            by_stage.setdefault(row.lifecycle_stage, []).append(meta.model_dump())
        allocated_pct = sum(
            float(r.capital_pct or 0)
            for r in rows
            if r.lifecycle_stage != LifecycleStage.RETIRED.value
        )
        self.db.flush()
        return {
            "total_capital": total,
            "allocated_pct": allocated_pct,
            "idle_pct": max(0.0, 1.0 - allocated_pct),
            "stage_labels": STAGE_LABELS,
            "by_stage": by_stage,
        }

    def _latest_row(self, strategy_id: str) -> StrategyRow | None:
        """取策略最新版本行。"""
        return self.db.scalar(
            select(StrategyRow)
            .where(StrategyRow.strategy_id == strategy_id)
            .order_by(StrategyRow.id.desc())
        )

    def _row_to_meta(self, row: StrategyRow) -> StrategyMeta:
        """ORM → StrategyMeta。"""
        return StrategyMeta(
            id=row.strategy_id,
            name=row.name,
            source=StrategySource(row.source),
            version=row.version,
            status=row.status,  # type: ignore[arg-type]
            lifecycle_stage=row.lifecycle_stage or "incubating",  # type: ignore[arg-type]
            description=row.description or "",
            capital_pct=float(row.capital_pct or 0),
            capital_allocated=float(row.capital_allocated or 0),
            kpi=json.loads(row.kpi_json or "{}"),
            lifecycle_history=json.loads(row.lifecycle_history_json or "[]"),
            entry_point=row.entry_point,
            yaml_body=row.yaml_body,
            params=json.loads(row.params_json or "{}"),
        )

    def _ensure_lifecycle_defaults(self, row: StrategyRow) -> StrategyRow:
        """为旧行补齐生命周期默认值。"""
        changed = False
        if not getattr(row, "lifecycle_stage", None):
            row.lifecycle_stage = status_to_lifecycle(row.status).value
            changed = True
        if row.kpi_json in (None, ""):
            row.kpi_json = "{}"
            changed = True
        if row.lifecycle_history_json in (None, ""):
            row.lifecycle_history_json = "[]"
            changed = True
        if row.description is None:
            row.description = ""
            changed = True
        if changed and not row.lifecycle_updated_at:
            row.lifecycle_updated_at = datetime.utcnow()
        return row

    def _apply_stage(
        self,
        row: StrategyRow,
        stage: LifecycleStage,
        *,
        reason: str,
        reset_promotion_days: bool,
    ) -> None:
        """写入阶段、资金建议与历史。"""
        old = row.lifecycle_stage or None
        row.lifecycle_stage = stage.value
        row.status = lifecycle_to_status(stage, current_status=row.status)
        pct = suggest_capital_pct(stage)
        total = float(get_settings().paper_initial_cash)
        row.capital_pct = pct
        row.capital_allocated = total * pct
        hist = json.loads(row.lifecycle_history_json or "[]")
        row.lifecycle_history_json = json.dumps(
            append_history(hist, from_stage=old, to_stage=stage.value, reason=reason),
            ensure_ascii=False,
        )
        kpi = StrategyKPI.from_dict(json.loads(row.kpi_json or "{}"))
        if reset_promotion_days:
            kpi.days_since_promotion = 0
            if stage != LifecycleStage.RETIRED:
                kpi.consecutive_low_sharpe_days = 0
        row.kpi_json = json.dumps(kpi.to_dict(), ensure_ascii=False)
        row.lifecycle_updated_at = datetime.utcnow()

    def _refresh_kpi_from_backtest(self, row: StrategyRow) -> None:
        """
        若 KPI 多为空，用最近一次回测报告填充收益/Sharpe/成交。

        注意：全样本 max_drawdown / 总收益不能当作「30 日滚动」指标去触发强制退役或
        自动填 IS/OOS，否则一点评估就会把策略全部标成退役并隐藏。
        """
        kpi = StrategyKPI.from_dict(json.loads(row.kpi_json or "{}"))
        if kpi.total_trades or kpi.rolling_30d_sharpe or kpi.rolling_30d_return:
            return
        run = self.db.scalar(
            select(BacktestRun)
            .where(BacktestRun.strategy_id == row.strategy_id)
            .order_by(BacktestRun.id.desc())
        )
        if not run:
            return
        kpi.rolling_30d_return = float(run.total_return or 0)
        kpi.rolling_30d_sharpe = float(run.sharpe or 0)
        kpi.total_trades = int(run.trades or 0)
        row.kpi_json = json.dumps(kpi.to_dict(), ensure_ascii=False)

    def restore_visible_strategies(self) -> int:
        """
        将误标为 archived 的策略恢复为可见（研究/孵化）。

        @returns: 恢复条数
        """
        rows = list(
            self.db.scalars(select(StrategyRow).where(StrategyRow.status == "archived")).all()
        )
        n = 0
        for row in rows:
            self._ensure_lifecycle_defaults(row)
            row.status = "research"
            self._apply_stage(
                row,
                LifecycleStage.INCUBATING,
                reason="恢复可见：撤销误退役/软删隐藏",
                reset_promotion_days=True,
            )
            n += 1
        self.db.flush()
        return n

    def _yaml_on_bar(self, data: dict[str, Any], ctx: Any) -> list[Signal]:
        """YAML 规则：factor_rules 通用求值；否则兼容旧 sma_fast/sma_slow。"""
        if isinstance(ctx, dict) and "db" not in ctx:
            ctx = {**ctx, "db": self.db}
        kind = str(data.get("kind") or "").strip().lower()
        if kind == "factor_rules" or (
            isinstance(data.get("buy"), dict) and "conditions" in (data.get("buy") or {})
        ):
            from desk_strategy.factor_rules import eval_factor_rules

            return eval_factor_rules(data, ctx)

        row = ctx.get("row") if isinstance(ctx, dict) else getattr(ctx, "row", {})
        when = data.get("when") or {}
        fast = int((when.get("sma_fast") or {}).get("period", 5))
        slow = int((when.get("sma_slow") or {}).get("period", 20))
        pf = row.get(f"sma_{fast}")
        ps = row.get(f"sma_{slow}")
        if pf is None or ps is None:
            return []
        symbol = row.get("symbol") or data.get("symbol") or "UNKNOWN"
        if pf > ps:
            return [Signal(symbol=symbol, side=Side.BUY, reason="sma_cross_up")]
        if pf < ps:
            return [Signal(symbol=symbol, side=Side.SELL, reason="sma_cross_down")]
        return []
