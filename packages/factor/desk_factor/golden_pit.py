"""黄金坑套件：无未来函数的日线序列（曲线 + 黄金坑/井喷）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 主曲线：通达信 VARE 语义（无未来）
_LINE_LLV = 34
_LINE_MA = 5
# 因果枢轴低点：用下一根确认（仅用到当前 bar）
_PIVOT_LEFT = 2
_PIT_MAX_AGE = 4  # 类似 TROUGHBARS<4
_PIT_FILTER = 3
_PIT_MARK = 50.0
_BLOWOFF_MARK = 50.0


def _ma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if n <= 0 or len(x) == 0:
        return out
    c = np.cumsum(np.nan_to_num(x, nan=0.0))
    for i in range(len(x)):
        if i + 1 < n:
            continue
        out[i] = (c[i] - (c[i - n] if i >= n else 0.0)) / n
    return out


def _llv(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(len(x)):
        start = max(0, i - n + 1)
        out[i] = float(np.nanmin(x[start : i + 1]))
    return out


def _hhv(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(len(x)):
        start = max(0, i - n + 1)
        out[i] = float(np.nanmax(x[start : i + 1]))
    return out


def _filter_signal(flags: np.ndarray, n: int) -> np.ndarray:
    """通达信 FILTER：信号后抑制 n 根。"""
    out = np.zeros(len(flags), dtype=float)
    suppress = 0
    for i, f in enumerate(flags):
        if suppress > 0:
            suppress -= 1
            continue
        if f:
            out[i] = 1.0
            suppress = n
    return out


def _causal_pivot_low(low: np.ndarray) -> np.ndarray:
    """
    在 bar i 确认 i-1 为枢轴低点：low[i-1] < low[i-1-k]（k=1..LEFT）且 low[i-1] < low[i]。
    仅使用 ≤i 的数据。
    """
    n = len(low)
    out = np.zeros(n, dtype=bool)
    for i in range(_PIVOT_LEFT + 1, n):
        j = i - 1
        ok = True
        for k in range(1, _PIVOT_LEFT + 1):
            if not (low[j] < low[j - k]):
                ok = False
                break
        if ok and low[j] < low[i]:
            out[i] = True
    return out


def _bars_since_event(events: np.ndarray) -> np.ndarray:
    out = np.full(len(events), np.nan)
    last = -10**9
    for i, e in enumerate(events):
        if e:
            last = i
        if last >= 0:
            out[i] = float(i - last)
    return out


def compute_golden_pit(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """
    计算黄金坑套件列。

    @param ohlcv 需含 open/high/low/close/volume（列名小写）；行按时间升序
    @returns 与输入等长的 gp_line / gp_pit / gp_blowoff
    """
    df = ohlcv.copy()
    rename = {c: str(c).lower() for c in df.columns}
    df = df.rename(columns=rename)
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    n = len(df)

    # gp_line ≈ MA(100*(C-LLV(C,34))/(HHV(H,34)-LLV(L,34)),5)-20
    den = _hhv(high, _LINE_LLV) - _llv(low, _LINE_LLV)
    raw = np.where(den > 1e-12, 100.0 * (close - _llv(close, _LINE_LLV)) / den, np.nan)
    gp_line = _ma(raw, _LINE_MA) - 20.0

    # 黄金坑：距最近已确认枢轴低点的 bar 数 < 4，再 FILTER
    piv = _causal_pivot_low(low)
    age = _bars_since_event(piv)
    raw_pit = np.array(
        [(np.isfinite(a) and a < _PIT_MAX_AGE and a >= 0) for a in age],
        dtype=bool,
    )
    # 排除「刚确认当根 age==0」的噪声：要求 0 < age < 4（落在波谷后数根内）
    raw_pit = np.array(
        [bool(np.isfinite(a) and 0 < a < _PIT_MAX_AGE) for a in age],
        dtype=bool,
    )
    gp_pit = _filter_signal(raw_pit, _PIT_FILTER) * _PIT_MARK

    # 井喷
    ref_c = np.roll(close, 1)
    ref_c[0] = np.nan
    ref_v = np.roll(vol, 1)
    ref_v[0] = np.nan
    ma_v5 = _ma(vol, 5)
    up = (close / ref_c) >= 1.099
    marubozu = (np.abs(open_ - low) < 1e-8) & (np.abs(high - close) < 1e-8)
    thin = (vol < ma_v5) & (vol < ref_v)
    cond = up & marubozu & thin & np.isfinite(ref_c)
    # COUNT(cond,20)==1 → 近 20 根（含当前）恰好 1 次为真，即当前为真且前 19 根无
    blow = np.zeros(n, dtype=float)
    for i in range(n):
        if not cond[i]:
            continue
        start = max(0, i - 19)
        if int(np.sum(cond[start : i + 1])) == 1:
            blow[i] = _BLOWOFF_MARK

    return pd.DataFrame(
        {"gp_line": gp_line, "gp_pit": gp_pit, "gp_blowoff": blow},
        index=df.index,
    )
