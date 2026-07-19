"""晨会强势股一键写入自选。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import MorningStrongPick
from desk_market import MarketService


def bind_morning_picks(
    db: Session,
    *,
    asof: date | None = None,
    limit: int = 20,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """
    将晨会个股选拔（或显式 symbols）写入自选。

    @param db: 会话
    @param asof: 交易日，默认今天
    @param limit: 最多写入只数
    @param symbols: 若提供则优先用此列表
    @returns: added / skipped / items
    """
    asof = asof or date.today()
    market = MarketService(db)
    items: list[dict[str, str]] = []
    if symbols:
        for sym in symbols[:limit]:
            items.append({"symbol": str(sym).strip().upper(), "name": ""})
    else:
        picks = db.scalars(
            select(MorningStrongPick)
            .where(
                MorningStrongPick.asof == asof,
                MorningStrongPick.pick_type != "board",
            )
            .order_by(MorningStrongPick.score.desc())
            .limit(limit)
        ).all()
        for p in picks:
            items.append({"symbol": str(p.code).upper(), "name": p.name or ""})

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
