"""FactorService.compute_series 契约。"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from desk_factor import FactorService


def _bars(n: int = 60) -> pd.DataFrame:
    start = date(2024, 1, 2)
    rows = []
    px = 100.0
    for i in range(n):
        px += 0.5
        d = start + timedelta(days=i)
        rows.append(
            {
                "date": d,
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px,
                "volume": 1000.0,
            }
        )
    return pd.DataFrame(rows)


def test_list_factors_wrapped_shape():
    rows = FactorService().list_factors()
    assert isinstance(rows, list)
    assert rows[0]["name"] == "SMA_5"
    assert "plot" in rows[0]
    assert "default_enabled" in rows[0]


def test_compute_series_returns_bars_and_outputs():
    out = FactorService().compute_series_from_df(_bars(), ["SMA_20", "RSI_14", "MACD"])
    assert out["engine"] in ("talib", "python")
    assert len(out["bars"]) == 60
    assert "sma_20" in out["series"]["SMA_20"]["outputs"]
    assert "rsi_14" in out["series"]["RSI_14"]["outputs"]
    assert set(out["series"]["MACD"]["outputs"]) >= {"macd", "macd_signal", "macd_hist"}
    vals = out["series"]["SMA_20"]["outputs"]["sma_20"]
    assert any(p["v"] is not None for p in vals)


def test_compute_series_unknown_name():
    with pytest.raises(ValueError, match="unknown"):
        FactorService().compute_series_from_df(_bars(30), ["NOPE"])
