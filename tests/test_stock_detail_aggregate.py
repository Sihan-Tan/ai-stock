"""日线聚合为周/月 K。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from desk_market.stock_detail import aggregate_ohlcv


def test_aggregate_week_and_month():
    rows = [
        {"date": date(2024, 1, 2), "open": 10, "high": 11, "low": 9.5, "close": 10.5, "volume": 100, "amount": 1000},
        {"date": date(2024, 1, 3), "open": 10.5, "high": 12, "low": 10, "close": 11, "volume": 200, "amount": 2200},
        {"date": date(2024, 1, 8), "open": 11, "high": 11.5, "low": 10.8, "close": 11.2, "volume": 150, "amount": 1650},
    ]
    df = pd.DataFrame(rows)
    week = aggregate_ohlcv(df, "week")
    assert len(week) >= 2
    assert week.iloc[0]["open"] == 10
    assert week.iloc[0]["close"] == 11
    assert week.iloc[0]["high"] == 12
    assert week.iloc[0]["volume"] == 300

    month = aggregate_ohlcv(df, "month")
    assert len(month) == 1
    assert month.iloc[0]["close"] == 11.2
