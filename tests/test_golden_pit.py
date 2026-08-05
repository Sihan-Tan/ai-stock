"""黄金坑套件：无未来波谷近似 + 井喷。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from desk_factor.golden_pit import compute_golden_pit


def _ohlcv(n: int, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 10 + np.cumsum(rng.normal(0, 0.2, size=n))
    high = close + rng.uniform(0.05, 0.4, size=n)
    low = close - rng.uniform(0.05, 0.4, size=n)
    open_ = close + rng.normal(0, 0.05, size=n)
    vol = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    dates = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m-%d") for d in dates],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


def test_compute_golden_pit_columns_and_length():
    df = _ohlcv(120)
    out = compute_golden_pit(df)
    assert list(out.columns) == ["gp_line", "gp_pit", "gp_blowoff"]
    assert len(out) == len(df)


def test_blowoff_triggers_on_limit_up_style_bar():
    """井喷：涨幅≥9.9% 且光头阳 + 缩量，且近 20 根内首次。"""
    n = 40
    df = _ohlcv(n, seed=1)
    # 构造第 30 根：开=低、收=高、相对昨收 +10%，量小于 MA5 且小于昨量
    i = 30
    df.loc[i - 1, "close"] = 10.0
    df.loc[i, "open"] = 10.0
    df.loc[i, "low"] = 10.0
    df.loc[i, "high"] = 11.0
    df.loc[i, "close"] = 11.0
    df.loc[i, "volume"] = 500_000.0
    for j in range(i - 5, i):
        df.loc[j, "volume"] = 2_000_000.0
    out = compute_golden_pit(df)
    assert float(out.loc[i, "gp_blowoff"]) != 0.0


def test_pit_is_causal_prefix_stable():
    """截断未来 bar 后，已有前缀的 gp_pit 不变。"""
    df = _ohlcv(80, seed=2)
    full = compute_golden_pit(df)
    prefix = compute_golden_pit(df.iloc[:60].reset_index(drop=True))
    a = full.iloc[:60]["gp_pit"].fillna(0).to_numpy()
    b = prefix["gp_pit"].fillna(0).to_numpy()
    assert np.allclose(a, b)


def test_gp_line_finite_after_warmup():
    df = _ohlcv(80)
    out = compute_golden_pit(df)
    # 34+5 预热后应有有限值
    assert np.isfinite(out["gp_line"].iloc[50])
