"""尾盘命中股一键写入自选。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import ClosingPick
from desk_market import MarketService


def bind_closing_picks(
    db: Session,
    *,
    asof: date | None = None,
    limit: int = 20,
    symbols: list[str] | None = None,
    strategy_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    将尾盘命中个股（或显式 symbols）写入自选。

    @param db: 会话
    @param asof: 交易日，默认今天
    @param limit: 最多写入只数
    @param symbols: 若提供则优先用此列表
    @param strategy_ids: 可选，按策略过滤 picks
    @returns: added / skipped / count
    """
    asof = asof or date.today()
    market = MarketService(db)
    items: list[dict[str, str]] = []
    if symbols:
        for sym in symbols[:limit]:
            items.append({"symbol": str(sym).strip().upper(), "name": ""})
    else:
        q = select(ClosingPick).where(ClosingPick.asof == asof)
        if strategy_ids:
            q = q.where(ClosingPick.strategy_id.in_(strategy_ids))
        picks = db.scalars(q.order_by(ClosingPick.score.desc())).all()
        seen: set[str] = set()
        for p in picks:
            sym = str(p.code).upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            items.append({"symbol": sym, "name": p.name or ""})
            if len(items) >= limit:
                break

    added: list[str] = []
    skipped: list[str] = []
    for it in items:
        sym = it["symbol"]
        if not sym:
            continue
        try:
            market.add_watchlist(sym, it.get("name") or sym)
            added.append(sym)
        except Exception:  # noqa: BLE001
            skipped.append(sym)
    db.flush()
    return {
        "asof": asof.isoformat(),
        "added": added,
        "skipped": skipped,
        "count": len(added),
    }
