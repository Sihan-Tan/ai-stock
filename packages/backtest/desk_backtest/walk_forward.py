"""Walk-Forward：样本内 / 样本外回测并计算 IS/OOS Sharpe 比。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from desk_common.contracts import BacktestRequest
from desk_market import MarketService


def is_oos_sharpe_ratio(is_sharpe: float | None, oos_sharpe: float | None) -> float:
    """
    计算 Walk-Forward IS/OOS 比例。

    @param is_sharpe: 样本内夏普
    @param oos_sharpe: 样本外夏普
    @returns: 比例（≥0）；IS≤0 且 OOS>0 时记 1.0
    """
    is_s = float(is_sharpe or 0.0)
    oos_s = float(oos_sharpe or 0.0)
    if is_s > 1e-9:
        return max(0.0, oos_s / is_s)
    if oos_s > 0:
        return 1.0
    return 0.0


def run_walk_forward(
    db: Session,
    *,
    strategy_id: str,
    symbol: str,
    start: date | None = None,
    end: date | None = None,
    is_fraction: float = 0.7,
    initial_cash: float = 1_000_000.0,
) -> dict[str, Any]:
    """
    按时间切分 IS/OOS，各跑一段回测（不落库子段），返回 KPI 字段。

    @param db: 会话
    @param strategy_id: 策略
    @param symbol: 标的
    @param start: 起始；默认 end-400 自然日
    @param end: 结束；默认今天
    @param is_fraction: 样本内占比
    @param initial_cash: 初始资金
    """
    from desk_backtest import BacktraderRunner

    end = end or date.today()
    start = start or (end - timedelta(days=400))
    is_fraction = min(0.9, max(0.5, float(is_fraction)))

    df = MarketService(db).load_daily_df(symbol, start, end)
    if df is None or getattr(df, "empty", True) or len(df) < 40:
        return {
            "status": "error",
            "strategy_id": strategy_id,
            "symbol": symbol,
            "message": "insufficient bars for walk-forward",
            "walk_forward_is_oos_ratio": 0.0,
        }

    dates = pd.to_datetime(df["date"]).dt.date.tolist()
    split_idx = max(20, int(len(dates) * is_fraction))
    split_idx = min(split_idx, len(dates) - 10)
    is_start, is_end = dates[0], dates[split_idx - 1]
    oos_start, oos_end = dates[split_idx], dates[-1]

    runner = BacktraderRunner(db)
    is_report = runner.run(
        BacktestRequest(
            strategy_id=strategy_id,
            symbol=symbol,
            start=is_start,
            end=is_end,
            initial_cash=initial_cash,
        ),
        persist=False,
    )
    oos_report = runner.run(
        BacktestRequest(
            strategy_id=strategy_id,
            symbol=symbol,
            start=oos_start,
            end=oos_end,
            initial_cash=initial_cash,
        ),
        persist=False,
    )
    ratio = is_oos_sharpe_ratio(is_report.sharpe, oos_report.sharpe)
    return {
        "status": "ok",
        "strategy_id": strategy_id,
        "symbol": symbol,
        "is_start": str(is_start),
        "is_end": str(is_end),
        "oos_start": str(oos_start),
        "oos_end": str(oos_end),
        "is_sharpe": is_report.sharpe,
        "oos_sharpe": oos_report.sharpe,
        "is_return": is_report.total_return,
        "oos_return": oos_report.total_return,
        "walk_forward_is_oos_ratio": ratio,
        "message": "",
    }
