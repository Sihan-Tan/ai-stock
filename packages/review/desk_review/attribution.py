"""归因：策略回测收益 vs 同期买入持有，并拆费用/胜率。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import BacktestRun
from desk_market import MarketService


def simple_vs_buyhold(db: Session, *, strategy_id: str | None = None) -> dict[str, Any]:
    """
    对最近一次回测做归因摘要。

    - buyhold：区间首末日线收盘价涨跌
    - active = strategy_return - buyhold
    - 成交胜率、费用合计、价差盈亏合计（来自 trade_list）

    @param db: 会话
    @param strategy_id: 可选策略过滤
    """
    q = select(BacktestRun).order_by(BacktestRun.id.desc())
    if strategy_id:
        q = q.where(BacktestRun.strategy_id == strategy_id)
    run = db.scalar(q.limit(1))
    if not run:
        return {"status": "empty", "message": "暂无回测记录，请先跑回测"}

    strat = float(run.total_return or 0)
    maxdd = float(run.max_drawdown or 0)
    sharpe = float(run.sharpe) if run.sharpe is not None else None

    report: dict[str, Any] = {}
    try:
        report = json.loads(run.report_json or "{}")
    except json.JSONDecodeError:
        report = {}

    trades = [t for t in (report.get("trade_list") or []) if t.get("status") != "open"]
    open_trades = [t for t in (report.get("trade_list") or []) if t.get("status") == "open"]

    wins = 0
    losses = 0
    fee_total = 0.0
    pnlcomm_sum = 0.0
    pnl_gross_sum = 0.0
    for t in trades:
        fee_total += float(t.get("fee_total") or t.get("commission") or 0)
        pc = t.get("pnlcomm")
        if pc is not None:
            pnlcomm_sum += float(pc)
            if float(pc) > 0:
                wins += 1
            elif float(pc) < 0:
                losses += 1
        pg = t.get("pnl")
        if pg is not None:
            pnl_gross_sum += float(pg)

    closed_n = len(trades)
    win_rate = (wins / closed_n) if closed_n else None
    fee_drag = (pnl_gross_sum - pnlcomm_sum) if closed_n else None

    # 同期买入持有：用回测起止日的日线
    bh = None
    bh_source = "unavailable"
    start = run.start_date
    end = run.end_date
    if start and end and run.symbol:
        df = MarketService(db).load_daily_df(run.symbol, start, end)
        if df is not None and not getattr(df, "empty", True) and len(df) >= 2:
            c0 = float(df.iloc[0]["close"])
            c1 = float(df.iloc[-1]["close"])
            if c0 > 0:
                bh = c1 / c0 - 1.0
                bh_source = "daily_bars"
    if bh is None and trades:
        first = float(trades[0].get("entry_price") or 0)
        last_t = trades[-1]
        last = float(last_t.get("exit_price") or last_t.get("mark_price") or 0)
        if first > 0 and last > 0:
            bh = last / first - 1.0
            bh_source = "trade_prices"

    active = (strat - bh) if bh is not None else None

    return {
        "status": "ok",
        "strategy_id": run.strategy_id,
        "symbol": run.symbol,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "strategy_return": strat,
        "buyhold_return": bh,
        "buyhold_source": bh_source,
        "active_return": active,
        "max_drawdown": maxdd,
        "sharpe": sharpe,
        "closed_trades": closed_n,
        "open_positions": len(open_trades),
        "win_rate": win_rate,
        "pnl_gross": pnl_gross_sum if closed_n else None,
        "pnl_net": pnlcomm_sum if closed_n else None,
        "fee_total": fee_total,
        "fee_drag": fee_drag,
        "message": (
            "策略总收益 vs 同期买入持有；active=超额。"
            f"买入持有来源={bh_source}。"
        ),
    }
