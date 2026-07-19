"""执行质量：纸成交价相对当日收盘的滑点代理。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import BarDaily, PaperAccount, PaperTrade


def analyze_paper_execution(db: Session, *, limit: int = 100) -> dict[str, Any]:
    """
    统计最近纸成交相对当日收盘的偏差（bps）。

    买：fill/close-1；卖：1-fill/close。正值表示相对收盘更差。

    @param db: 会话
    @param limit: 最近成交条数
    """
    acc = db.scalar(select(PaperAccount).where(PaperAccount.name == "default"))
    if not acc:
        return {"trades": 0, "avg_slip_bps": None, "items": []}
    trades = db.scalars(
        select(PaperTrade)
        .where(PaperTrade.account_id == acc.id)
        .order_by(PaperTrade.id.desc())
        .limit(limit)
    ).all()
    items: list[dict[str, Any]] = []
    slips: list[float] = []
    for t in trades:
        day = t.created_at.date() if t.created_at else None
        close = None
        if day:
            bar = db.scalar(
                select(BarDaily).where(BarDaily.symbol == t.symbol, BarDaily.ts == day)
            )
            if bar:
                close = float(bar.close)
        slip_bps = None
        if close and close > 0 and t.price:
            if t.side == "buy":
                slip_bps = (float(t.price) / close - 1.0) * 10_000
            else:
                slip_bps = (1.0 - float(t.price) / close) * 10_000
            slips.append(slip_bps)
        items.append(
            {
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "qty": t.qty,
                "price": t.price,
                "close": close,
                "slip_bps": slip_bps,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
        )
    avg = sum(slips) / len(slips) if slips else None
    return {
        "trades": len(trades),
        "with_bar": len(slips),
        "avg_slip_bps": avg,
        "items": items,
    }
