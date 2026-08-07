"""持仓建议标的名称解析。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import QuoteSnapshot, SecurityMeta


def resolve_symbol_names(db: Session, symbols: list[str]) -> dict[str, str]:
    """
    批量解析股票名称。

    优先 ``quotes_snapshot.name``，缺失再查 ``SecurityMeta``。

    @param db: 数据库 Session
    @param symbols: 标的代码列表
    @returns: symbol → name（仅含解析到非空名称的项）
    """
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = normalize_symbol(str(raw or ""))
        if not sym or sym in seen:
            continue
        seen.add(sym)
        uniq.append(sym)
    if not uniq:
        return {}

    out: dict[str, str] = {}
    for row in db.scalars(select(QuoteSnapshot).where(QuoteSnapshot.symbol.in_(uniq))).all():
        name = str(row.name or "").strip()
        if name:
            out[str(row.symbol)] = name

    missing = [s for s in uniq if s not in out]
    if not missing:
        return out

    for row in db.scalars(select(SecurityMeta).where(SecurityMeta.symbol.in_(missing))).all():
        name = str(row.name or "").strip()
        if name:
            out[str(row.symbol)] = name
    return out
