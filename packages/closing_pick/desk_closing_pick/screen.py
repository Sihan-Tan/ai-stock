"""单策略 × 单标的买入信号求值（不下单）。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import yaml
from sqlalchemy.orm import Session

from desk_common.contracts import Side
from desk_market import MarketService
from desk_strategy import StrategyRegistry
from desk_strategy.bar_context import build_bar_row
from desk_strategy.factor_rules import attach_ml_factor_columns, collect_factor_names


def eval_buy_signals(
    db: Session, *, strategy_id: str, symbol: str, asof: date | None = None
) -> dict[str, Any]:
    """
    评估最新日 K 的买入信号。

    复用纸交易 Runner 的日线加载与 on_bar 路径，但只收集 BUY、不下单。

    @param db: 数据库会话
    @param strategy_id: 策略 ID
    @param symbol: 标的代码
    @param asof: 业务截止日；缺省为今天
    @returns: ok / signals / bar_date / last_close / message / pct_chg
    """
    base: dict[str, Any] = {
        "ok": False,
        "signals": [],
        "bar_date": None,
        "last_close": None,
        "pct_chg": None,
        "message": "",
    }
    reg = StrategyRegistry(db).load(strategy_id)
    if not reg or not reg.on_bar:
        base["message"] = f"strategy not runnable: {strategy_id}"
        return base

    end = asof or date.today()
    start = end - timedelta(days=400)
    df = MarketService(db).load_daily_df(symbol, start, end)
    if df is None or getattr(df, "empty", True) or len(df) < 30:
        base["message"] = "insufficient bars"
        return base

    history = df.copy()
    body = getattr(reg.meta, "yaml_body", None) or ""
    parsed = yaml.safe_load(body) if body else None
    if isinstance(parsed, dict):
        history = attach_ml_factor_columns(
            history, collect_factor_names(parsed), db
        )

    idx = len(df) - 1
    lookback = min(250, idx + 1)
    slice_df = df.iloc[idx + 1 - lookback : idx + 1]
    row = build_bar_row(
        symbol,
        closes=slice_df["close"].astype(float).tolist(),
        highs=slice_df["high"].astype(float).tolist(),
        lows=slice_df["low"].astype(float).tolist(),
        opens=slice_df["open"].astype(float).tolist(),
        volumes=slice_df["volume"].astype(float).tolist(),
    )
    signals = reg.on_bar({"row": row, "history": history, "db": db}) or []
    buys = []
    for s in signals:
        side = s.side if hasattr(s, "side") else Side(str(s.get("side")))
        if side == Side.BUY:
            buys.append(s.model_dump() if hasattr(s, "model_dump") else dict(s))

    last = df.iloc[-1]
    prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
    last_close = float(last["close"])
    pct = (last_close / prev_close - 1.0) if prev_close else 0.0
    # load_daily_df 将 BarDaily.ts 映射为列 "date"（非 index）
    bar_date = last["date"] if "date" in df.columns else None
    if hasattr(bar_date, "date"):
        bar_date = bar_date.date()
    elif hasattr(bar_date, "isoformat"):
        pass
    else:
        bar_date = None

    base.update(
        {
            "ok": True,
            "signals": buys,
            "bar_date": bar_date.isoformat() if bar_date else None,
            "last_close": last_close,
            "pct_chg": round(pct, 6),
            "message": "",
        }
    )
    return base
