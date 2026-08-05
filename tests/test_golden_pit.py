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


def _deep_v_frame() -> pd.DataFrame:
    """构造：冲高 → 深跌超 15% → 再反弹超 15%。"""
    n = 60
    close = np.full(n, 20.0)
    for i in range(0, 8):
        close[i] = 20.0 + i * 0.3  # 冲高
    peak = close[7]
    for i in range(8, 31):
        close[i] = peak - (i - 7) * 0.35
    trough_i = int(np.argmin(close[:35]))
    trough_px = close[trough_i]
    for i in range(trough_i + 1, 55):
        close[i] = trough_px + (i - trough_i) * 0.2
    high = close + 0.05
    low = close - 0.05
    low[trough_i] = trough_px - 0.4
    return pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-01", periods=n)],
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(n, 1e6),
        }
    ), trough_i


def test_compute_golden_pit_columns_and_length():
    df = _ohlcv(120)
    out = compute_golden_pit(df)
    assert list(out.columns) == ["gp_line", "gp_pit", "gp_blowoff"]
    assert len(out) == len(df)


def test_blowoff_triggers_on_limit_up_style_bar():
    """井喷：涨幅≥9.9% 且光头阳 + 缩量，且近 20 根内首次。"""
    n = 40
    df = _ohlcv(n, seed=1)
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


def test_gp_line_finite_after_warmup():
    df = _ohlcv(80)
    out = compute_golden_pit(df)
    assert np.isfinite(out["gp_line"].iloc[50])


def test_shallow_noise_does_not_mark_pit():
    """小幅震荡（远小于转折百分比）不应标黄金坑。"""
    n = 80
    close = np.full(n, 10.0)
    for i in range(n):
        close[i] = 10.0 + (0.08 if i % 2 == 0 else -0.08)
    df = pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-01", periods=n)],
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": np.full(n, 1e6),
        }
    )
    out = compute_golden_pit(df)
    assert int((out["gp_pit"] != 0).sum()) == 0


def test_deep_v_marks_on_trough_bar():
    """确认后信号回标到谷底 K，而非确认日。"""
    df, trough_i = _deep_v_frame()
    out = compute_golden_pit(df)
    pit_idx = [i for i, v in enumerate(out["gp_pit"].to_numpy()) if v != 0]
    assert pit_idx, "应至少有一个黄金坑标记"
    # FILTER 后首个标记应落在谷底（回标）
    assert pit_idx[0] == trough_i
    # 不应只出现在远离谷底的确认日：谷底 low 应不高于邻域
    assert float(df.loc[trough_i, "low"]) <= float(df.loc[trough_i - 1, "low"])
    assert float(df.loc[trough_i, "low"]) <= float(df.loc[trough_i + 1, "low"])
