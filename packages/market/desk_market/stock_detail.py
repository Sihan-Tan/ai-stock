"""单标的详情：聚合、meta、板块、资金、技术面。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BoardMember, SecurityMeta
from desk_indicators import compute


def _f(v: Any) -> float | None:
    """
    将指标值转为 float；NaN / None → None。

    @param v: 原始标量
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def aggregate_ohlcv(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """
    将日线 OHLCV 聚合为周/月。

    @param df: 需含 date/open/high/low/close/volume/amount
    @param period: week | month
    """
    if df.empty:
        return df.copy()
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date")
    freq = "W-FRI" if period == "week" else "ME"
    grouped = out.set_index("date").resample(freq)
    agg = grouped.agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        }
    ).dropna(subset=["open"])
    agg = agg.reset_index()
    agg["date"] = agg["date"].dt.date
    return agg


def get_security_meta(db: Session, symbol: str) -> dict | None:
    """
    读取标的元数据。

    @param db: 数据库 Session
    @param symbol: 标的代码
    @returns: 元数据 dict，不存在则 None
    """
    sym = normalize_symbol(symbol)
    row = db.scalar(select(SecurityMeta).where(SecurityMeta.symbol == sym))
    if row is None:
        return None
    return {
        "symbol": row.symbol,
        "name": row.name,
        "is_delisted": row.is_delisted,
        "status": row.status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_boards_for_symbol(db: Session, symbol: str) -> list[dict]:
    """
    读取标的当前所属板块/概念。

    @param db: 数据库 Session
    @param symbol: 标的代码
    @returns: 板块列表（仅 effective_to 为空的有效成分）
    """
    sym = normalize_symbol(symbol)
    rows = db.scalars(
        select(BoardMember).where(
            BoardMember.symbol == sym,
            BoardMember.effective_to.is_(None),
        )
    ).all()
    return [
        {
            "board_code": r.board_code,
            "board_name": r.board_name,
            "board_type": r.board_type,
        }
        for r in rows
    ]


def compute_technicals(db: Session, symbol: str, *, lookback_days: int = 180) -> dict:
    """
    基于库内日线计算 MA / MACD / RSI。

    @param db: 数据库 Session
    @param symbol: 标的代码
    @param lookback_days: 回溯自然日数
    @returns: available / latest / series 等字段
    """
    from desk_market import MarketService

    sym = normalize_symbol(symbol)
    to = date.today()
    fr = to - timedelta(days=lookback_days)
    df = MarketService(db).load_daily_df(sym, fr, to, adj=None)
    if df is None or df.empty or len(df) < 30:
        return {"available": False, "error": "insufficient bars", "symbol": sym}

    work = df.copy()
    if "date" not in work.columns and "ts" in work.columns:
        work = work.rename(columns={"ts": "date"})
    work = work.sort_values("date")
    ind = compute(work, ["SMA_5", "SMA_10", "SMA_20", "RSI_14", "MACD"])
    last = ind.iloc[-1]

    def _row_point(row: pd.Series) -> dict:
        d = row.get("date")
        return {
            "date": str(d)[:10] if d is not None else None,
            "ma5": _f(row.get("sma_5")),
            "ma10": _f(row.get("sma_10")),
            "ma20": _f(row.get("sma_20")),
            "macd": _f(row.get("macd")),
            "macd_signal": _f(row.get("macd_signal")),
            "macd_hist": _f(row.get("macd_hist")),
            "rsi14": _f(row.get("rsi_14")),
        }

    series = [_row_point(row) for _, row in ind.iterrows()]
    return {
        "available": True,
        "symbol": sym,
        "source": "db",
        "as_of": str(last.get("date", ""))[:10],
        "latest": {
            "ma5": _f(last.get("sma_5")),
            "ma10": _f(last.get("sma_10")),
            "ma20": _f(last.get("sma_20")),
            "macd": _f(last.get("macd")),
            "macd_signal": _f(last.get("macd_signal")),
            "macd_hist": _f(last.get("macd_hist")),
            "rsi14": _f(last.get("rsi_14")),
        },
        "series": series,
    }
