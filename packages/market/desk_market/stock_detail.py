"""单标的详情：聚合、meta、板块、资金、技术面。"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BoardMember, SecurityMeta


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
