"""技术指标：优先 TA-Lib，不可用时回退 pandas/numpy。"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

try:
    import talib as _talib  # type: ignore

    HAS_TALIB = True
except Exception:  # pragma: no cover
    _talib = None
    HAS_TALIB = False


def compute(ohlcv: pd.DataFrame, specs: Iterable[str] | None = None) -> pd.DataFrame:
    """
    计算常用技术指标。

    @param ohlcv: 需含 open/high/low/close/volume
    @param specs: 指标名列表；默认 SMA_5/SMA_20/EMA_12/RSI_14/MACD/ATR_14/BOLL
    @returns: 原表附加指标列
    """
    df = ohlcv.copy()
    close = df["close"].astype(float).values
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    specs = list(specs or ["SMA_5", "SMA_20", "EMA_12", "RSI_14", "MACD", "ATR_14", "BOLL"])

    for spec in specs:
        key = spec.upper()
        if key.startswith("SMA_"):
            n = int(key.split("_")[1])
            df[f"sma_{n}"] = _sma(close, n)
        elif key.startswith("EMA_"):
            n = int(key.split("_")[1])
            df[f"ema_{n}"] = _ema(close, n)
        elif key.startswith("RSI_"):
            n = int(key.split("_")[1])
            df[f"rsi_{n}"] = _rsi(close, n)
        elif key == "MACD":
            macd, signal, hist = _macd(close)
            df["macd"], df["macd_signal"], df["macd_hist"] = macd, signal, hist
        elif key.startswith("ATR_"):
            n = int(key.split("_")[1])
            df[f"atr_{n}"] = _atr(high, low, close, n)
        elif key == "BOLL":
            mid, upper, lower = _boll(close, 20, 2)
            df["boll_mid"], df["boll_upper"], df["boll_lower"] = mid, upper, lower
    return df


def _sma(close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.SMA(close, timeperiod=n)
    return pd.Series(close).rolling(n).mean().to_numpy()


def _ema(close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.EMA(close, timeperiod=n)
    return pd.Series(close).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.RSI(close, timeperiod=n)
    s = pd.Series(close)
    delta = s.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    down = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).to_numpy()


def _macd(close: np.ndarray):
    if HAS_TALIB:
        return _talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean()
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd.to_numpy(), signal.to_numpy(), hist.to_numpy()


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.ATR(high, low, close, timeperiod=n)
    prev_close = pd.Series(close).shift(1)
    tr = pd.concat(
        [
            pd.Series(high) - pd.Series(low),
            (pd.Series(high) - prev_close).abs(),
            (pd.Series(low) - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean().to_numpy()


def _boll(close: np.ndarray, n: int, k: float):
    if HAS_TALIB:
        upper, mid, lower = _talib.BBANDS(close, timeperiod=n, nbdevup=k, nbdevdn=k)
        return mid, upper, lower
    s = pd.Series(close)
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid.to_numpy(), (mid + k * std).to_numpy(), (mid - k * std).to_numpy()
