"""执行质量：纸成交相对当日收盘/配置滑点的统计。"""

from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_db.models import BarDaily, PaperAccount, PaperTrade


def _percentile(values: list[float], q: float) -> float | None:
    """分位数；空序列返回 None。"""
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q))


def analyze_paper_execution(db: Session, *, limit: int = 200) -> dict[str, Any]:
    """
    统计最近纸成交执行质量。

    - 滑点代理：买 fill/close-1，卖 1-fill/close（正值=相对收盘更差），单位 bps
    - 对比配置滑点 ``BACKTEST_SLIPPAGE``
    - 分买/卖、分位数、成交额

    @param db: 会话
    @param limit: 最近成交条数
    """
    settings = get_settings()
    cfg_slip_bps = float(settings.backtest_slippage or 0) * 10_000
    acc = db.scalar(select(PaperAccount).where(PaperAccount.name == "default"))
    empty = {
        "trades": 0,
        "with_bar": 0,
        "avg_slip_bps": None,
        "median_slip_bps": None,
        "p95_slip_bps": None,
        "buy_avg_slip_bps": None,
        "sell_avg_slip_bps": None,
        "configured_slip_bps": cfg_slip_bps,
        "slip_vs_config_bps": None,
        "buy_count": 0,
        "sell_count": 0,
        "total_notional": 0.0,
        "items": [],
        "message": "暂无纸成交",
    }
    if not acc:
        return empty

    trades = db.scalars(
        select(PaperTrade)
        .where(PaperTrade.account_id == acc.id)
        .order_by(PaperTrade.id.desc())
        .limit(limit)
    ).all()
    if not trades:
        return empty

    items: list[dict[str, Any]] = []
    all_slips: list[float] = []
    buy_slips: list[float] = []
    sell_slips: list[float] = []
    buy_count = 0
    sell_count = 0
    total_notional = 0.0

    for t in trades:
        day = t.created_at.date() if t.created_at else None
        close = None
        if day:
            bar = db.scalar(
                select(BarDaily).where(BarDaily.symbol == t.symbol, BarDaily.ts == day)
            )
            if bar:
                close = float(bar.close)
        notional = float(t.price or 0) * float(t.qty or 0)
        total_notional += notional
        if t.side == "buy":
            buy_count += 1
        else:
            sell_count += 1

        slip_bps = None
        if close and close > 0 and t.price:
            if t.side == "buy":
                slip_bps = (float(t.price) / close - 1.0) * 10_000
                buy_slips.append(slip_bps)
            else:
                slip_bps = (1.0 - float(t.price) / close) * 10_000
                sell_slips.append(slip_bps)
            all_slips.append(slip_bps)

        items.append(
            {
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "qty": t.qty,
                "price": t.price,
                "notional": notional,
                "close": close,
                "slip_bps": slip_bps,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
        )

    avg = sum(all_slips) / len(all_slips) if all_slips else None
    return {
        "trades": len(trades),
        "with_bar": len(all_slips),
        "avg_slip_bps": avg,
        "median_slip_bps": _percentile(all_slips, 50),
        "p95_slip_bps": _percentile(all_slips, 95),
        "buy_avg_slip_bps": sum(buy_slips) / len(buy_slips) if buy_slips else None,
        "sell_avg_slip_bps": sum(sell_slips) / len(sell_slips) if sell_slips else None,
        "configured_slip_bps": cfg_slip_bps,
        "slip_vs_config_bps": (avg - cfg_slip_bps) if avg is not None else None,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "total_notional": total_notional,
        "items": items,
        "message": (
            "滑点=成交价相对当日收盘；正值表示更差。"
            f"配置滑点约 {cfg_slip_bps:.1f} bps。"
        ),
    }
