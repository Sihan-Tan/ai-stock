"""GOLDEN_PIT 经 FactorService 出序列。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from desk_factor import FactorService


def test_compute_series_from_df_golden_pit():
    n = 100
    rng = np.random.default_rng(0)
    close = 10 + np.cumsum(rng.normal(0, 0.1, n))
    df = pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-01", periods=n)],
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": np.full(n, 1e6),
        }
    )
    out = FactorService(db=None).compute_series_from_df(df, ["GOLDEN_PIT"])
    block = out["series"]["GOLDEN_PIT"]["outputs"]
    assert set(block) == {"gp_line", "gp_pit", "gp_blowoff"}
    assert len(block["gp_line"]) == n
