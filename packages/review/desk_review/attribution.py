"""轻量归因：单标的策略收益相对买入持有。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import BacktestRun


def simple_vs_buyhold(db: Session, *, strategy_id: str | None = None) -> dict[str, Any]:
    """
    用最近回测总收益 vs 同期（报告内无法精确 buy&hold 时）给出占位对比。

    若有 report_json 权益曲线，则用首尾价估算 buy&hold。

    @param db: 会话
    @param strategy_id: 可选策略过滤
    """
    import json

    q = select(BacktestRun).order_by(BacktestRun.id.desc())
    if strategy_id:
        q = q.where(BacktestRun.strategy_id == strategy_id)
    run = db.scalar(q.limit(1))
    if not run:
        return {"status": "empty", "message": "no backtest run"}
    bh = None
    try:
        report = json.loads(run.report_json or "{}")
        curve = report.get("equity_curve") or []
        # 无标的价格曲线时，用权益曲线无法得 buyhold；尝试 trade_list 首末价
        trades = [t for t in (report.get("trade_list") or []) if t.get("status") != "open"]
        if trades:
            first = float(trades[0].get("entry_price") or 0)
            last_t = trades[-1]
            last = float(last_t.get("exit_price") or last_t.get("mark_price") or 0)
            if first > 0 and last > 0:
                bh = last / first - 1.0
        elif len(curve) >= 2:
            # 退化：无法分离 alpha，仅返回策略收益
            bh = None
    except (json.JSONDecodeError, TypeError, ValueError):
        bh = None
    strat = float(run.total_return or 0)
    alpha = (strat - bh) if bh is not None else None
    return {
        "status": "ok",
        "strategy_id": run.strategy_id,
        "symbol": run.symbol,
        "strategy_return": strat,
        "buyhold_return": bh,
        "active_return": alpha,
        "message": "轻量对比：策略总收益 vs 成交首末价买入持有",
    }
