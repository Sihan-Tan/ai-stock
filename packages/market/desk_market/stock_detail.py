"""单标的详情：聚合、meta、板块、资金、技术面。"""

from __future__ import annotations

import pandas as pd


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
