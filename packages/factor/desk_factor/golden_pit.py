"""黄金坑套件：无未来函数的日线序列（曲线 + 黄金坑/井喷）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 主曲线：通达信 VARE 语义（无未来）
_LINE_LLV = 34
_LINE_MA = 5
# 通达信 TROUGHBARS(3,15,1) 的 N 为转折百分比；过稀可改为 5
_ZIG_PCT = 15.0
# 相对谷底若干根内可出信号窗（对应 TROUGHBARS<4）；展示回标到谷底
_PIT_MAX_AGE = 4
_PIT_FILTER = 5  # 与脚本 STICKLINE(FILTER(...,5)) 对齐
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


def _zigzag_trough_pairs(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    pct: float,
) -> list[tuple[int, int]]:
    """
    因果百分比之字转向，返回 (谷底索引, 确认日索引) 列表。

    确认仍只用到确认日及之前的数据；展示层可将信号回标到谷底日。

    @param high 最高价
    @param low 最低价
    @param close 收盘价
    @param pct 转折百分比
    """
    n = len(close)
    pairs: list[tuple[int, int]] = []
    if n == 0 or pct <= 0:
        return pairs

    thr = pct / 100.0
    seeking_high = True
    ext_idx = 0
    ext_high = high[0]
    ext_low = low[0]

    for i in range(1, n):
        if seeking_high:
            if high[i] >= ext_high:
                ext_high = high[i]
                ext_idx = i
            if ext_high > 0 and (ext_high - close[i]) / ext_high >= thr and ext_idx < i:
                seeking_high = False
                ext_low = low[i]
                ext_idx = i
        else:
            if low[i] <= ext_low:
                ext_low = low[i]
                ext_idx = i
            if ext_low > 0 and (close[i] - ext_low) / ext_low >= thr and ext_idx < i:
                pairs.append((ext_idx, i))
                seeking_high = True
                ext_high = high[i]
                ext_idx = i

    return pairs


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

    den = _hhv(high, _LINE_LLV) - _llv(low, _LINE_LLV)
    raw = np.where(den > 1e-12, 100.0 * (close - _llv(close, _LINE_LLV)) / den, np.nan)
    gp_line = _ma(raw, _LINE_MA) - 20.0

    # 反弹确认后，把信号回标到谷底及随后 age<_PIT_MAX_AGE（且不超过确认日）
    raw_pit = np.zeros(n, dtype=bool)
    for trough_i, confirm_i in _zigzag_trough_pairs(high, low, close, _ZIG_PCT):
        end = min(confirm_i, trough_i + _PIT_MAX_AGE - 1)
        for j in range(trough_i, end + 1):
            raw_pit[j] = True
    gp_pit = _filter_signal(raw_pit, _PIT_FILTER) * _PIT_MARK

    ref_c = np.roll(close, 1)
    ref_c[0] = np.nan
    ref_v = np.roll(vol, 1)
    ref_v[0] = np.nan
    ma_v5 = _ma(vol, 5)
    up = (close / ref_c) >= 1.099
    marubozu = (np.abs(open_ - low) < 1e-8) & (np.abs(high - close) < 1e-8)
    thin = (vol < ma_v5) & (vol < ref_v)
    cond = up & marubozu & thin & np.isfinite(ref_c)
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
