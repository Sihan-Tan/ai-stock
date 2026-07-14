"""策略注册与 YAML / Agent 草稿。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.contracts import Side, Signal, StrategyMeta, StrategySource
from desk_db.models import StrategyRow

_REGISTRY: dict[str, "RegisteredStrategy"] = {}


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
        def _on_bar(ctx):
            if hasattr(cls_or_fn, "on_bar"):
                inst = cls_or_fn() if isinstance(cls_or_fn, type) else cls_or_fn
                return inst.on_bar(ctx) if hasattr(inst, "on_bar") else cls_or_fn(ctx)
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
        # 触发示例策略导入
        import desk_strategy.strategies.ma_cross  # noqa: F401

        n = 0
        for sid, reg in _REGISTRY.items():
            existing = self.db.scalar(
                select(StrategyRow).where(
                    StrategyRow.strategy_id == sid, StrategyRow.version == reg.meta.version
                )
            )
            if existing:
                continue
            self.db.add(
                StrategyRow(
                    strategy_id=sid,
                    name=reg.meta.name,
                    source="python",
                    version=reg.meta.version,
                    status=reg.meta.status,
                    entry_point=reg.meta.entry_point,
                    params_json=json.dumps(reg.meta.params, ensure_ascii=False),
                )
            )
            n += 1
        self.db.flush()
        return n

    def from_yaml(self, doc: str | dict[str, Any], status: str = "research") -> StrategyMeta:
        """解析 YAML 并入库。"""
        data = yaml.safe_load(doc) if isinstance(doc, str) else doc
        sid = str(data["id"])
        meta = StrategyMeta(
            id=sid,
            name=data.get("name", sid),
            source=StrategySource.YAML,
            version=str(data.get("version", "v0.1")),
            status=status,  # type: ignore[arg-type]
            yaml_body=yaml.safe_dump(data, allow_unicode=True),
            params=data.get("params") or {},
        )
        self._upsert_row(meta)
        _REGISTRY[sid] = RegisteredStrategy(
            meta=meta,
            on_bar=lambda ctx, d=data: self._yaml_on_bar(d, ctx),
        )
        return meta

    def save_agent_draft(self, payload: dict[str, Any]) -> StrategyMeta:
        """Agent 草稿（默认 draft）。"""
        body = payload.get("yaml_body") or payload
        if isinstance(body, str):
            data = yaml.safe_load(body)
        else:
            data = dict(body)
        data["id"] = data.get("id") or payload.get("id") or "agent_draft"
        meta = self.from_yaml(data, status="draft")
        meta.source = StrategySource.AGENT
        row = self.db.scalar(
            select(StrategyRow).where(
                StrategyRow.strategy_id == meta.id, StrategyRow.version == meta.version
            )
        )
        if row:
            row.source = "agent"
            row.status = "draft"
        self.db.flush()
        return meta

    def promote(self, strategy_id: str, to_status: str = "research") -> StrategyMeta | None:
        """草稿晋级。"""
        row = self.db.scalar(
            select(StrategyRow)
            .where(StrategyRow.strategy_id == strategy_id)
            .order_by(StrategyRow.id.desc())
        )
        if not row:
            return None
        row.status = to_status
        self.db.flush()
        return StrategyMeta(
            id=row.strategy_id,
            name=row.name,
            source=StrategySource(row.source),
            version=row.version,
            status=row.status,  # type: ignore[arg-type]
            entry_point=row.entry_point,
            yaml_body=row.yaml_body,
            params=json.loads(row.params_json or "{}"),
        )

    def list(self, source: str | None = None) -> list[StrategyMeta]:
        """列出策略。"""
        self.sync_python_to_db()
        q = select(StrategyRow).order_by(StrategyRow.id.desc())
        if source:
            q = q.where(StrategyRow.source == source)
        rows = self.db.scalars(q).all()
        return [
            StrategyMeta(
                id=r.strategy_id,
                name=r.name,
                source=StrategySource(r.source),
                version=r.version,
                status=r.status,  # type: ignore[arg-type]
                entry_point=r.entry_point,
                yaml_body=r.yaml_body,
                params=json.loads(r.params_json or "{}"),
            )
            for r in rows
        ]

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

    def _upsert_row(self, meta: StrategyMeta) -> None:
        existing = self.db.scalar(
            select(StrategyRow).where(
                StrategyRow.strategy_id == meta.id, StrategyRow.version == meta.version
            )
        )
        if existing:
            existing.name = meta.name
            existing.source = meta.source.value
            existing.status = meta.status
            existing.yaml_body = meta.yaml_body
            existing.entry_point = meta.entry_point
            existing.params_json = json.dumps(meta.params, ensure_ascii=False)
        else:
            self.db.add(
                StrategyRow(
                    strategy_id=meta.id,
                    name=meta.name,
                    source=meta.source.value,
                    version=meta.version,
                    status=meta.status,
                    entry_point=meta.entry_point,
                    yaml_body=meta.yaml_body,
                    params_json=json.dumps(meta.params, ensure_ascii=False),
                )
            )
        self.db.flush()

    @staticmethod
    def _yaml_on_bar(data: dict[str, Any], ctx: Any) -> list[Signal]:
        """极简 YAML 规则：当 sma_fast > sma_slow 买入，反之卖出。"""
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
