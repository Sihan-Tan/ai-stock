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

_LAST_ENGINE: str = "python"


def last_engine() -> str:
    """返回最近一次 compute 使用的计算引擎。"""
    return _LAST_ENGINE


def _mark_python_engine() -> None:
    global _LAST_ENGINE
    _LAST_ENGINE = "python"


def compute(ohlcv: pd.DataFrame, specs: Iterable[str] | None = None) -> pd.DataFrame:
    """
    计算常用技术指标。

    @param ohlcv: 需含 open/high/low/close/volume
    @param specs: 指标名列表；默认 SMA_5/SMA_20/EMA_12/RSI_14/MACD/ATR_14/BOLL
    @returns: 原表附加指标列
    """
    global _LAST_ENGINE
    _LAST_ENGINE = "talib" if HAS_TALIB else "python"

    df = ohlcv.copy()
    close = df["close"].astype(float).values
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    volume = df["volume"].astype(float).values
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
        elif key == "STOCH":
            stoch_k, stoch_d = _stoch(high, low, close)
            df["stoch_k"], df["stoch_d"] = stoch_k, stoch_d
        elif key.startswith("CCI_"):
            n = int(key.split("_")[1])
            df[f"cci_{n}"] = _cci(high, low, close, n)
        elif key.startswith("ADX_"):
            n = int(key.split("_")[1])
            df[f"adx_{n}"] = _adx(high, low, close, n)
        elif key == "OBV":
            df["obv"] = _obv(close, volume)
        elif key.startswith("MOM_"):
            n = int(key.split("_")[1])
            df[f"mom_{n}"] = _mom(close, n)
        elif key.startswith("WILLR_"):
            n = int(key.split("_")[1])
            df[f"willr_{n}"] = _willr(high, low, close, n)
        else:
            raise ValueError(f"unknown indicator: {spec}")
    return df


def _sma(close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.SMA(close, timeperiod=n)
    _mark_python_engine()
    return pd.Series(close).rolling(n).mean().to_numpy()


def _ema(close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.EMA(close, timeperiod=n)
    _mark_python_engine()
    return pd.Series(close).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.RSI(close, timeperiod=n)
    _mark_python_engine()
    s = pd.Series(close)
    delta = s.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    down = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).to_numpy()


def _macd(close: np.ndarray):
    if HAS_TALIB:
        return _talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    _mark_python_engine()
    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean()
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd.to_numpy(), signal.to_numpy(), hist.to_numpy()


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.ATR(high, low, close, timeperiod=n)
    _mark_python_engine()
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
    _mark_python_engine()
    s = pd.Series(close)
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid.to_numpy(), (mid + k * std).to_numpy(), (mid - k * std).to_numpy()


def _stoch(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fastk: int = 5,
    slowk: int = 3,
    slowd: int = 3,
):
    if HAS_TALIB:
        return _talib.STOCH(
            high,
            low,
            close,
            fastk_period=fastk,
            slowk_period=slowk,
            slowd_period=slowd,
        )
    _mark_python_engine()
    lowest_low = pd.Series(low).rolling(fastk).min()
    highest_high = pd.Series(high).rolling(fastk).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    fast_k = 100 * (pd.Series(close) - lowest_low) / denom
    slow_k = fast_k.rolling(slowk).mean()
    slow_d = slow_k.rolling(slowd).mean()
    return slow_k.to_numpy(), slow_d.to_numpy()


def _cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.CCI(high, low, close, timeperiod=n)
    _mark_python_engine()
    tp = (pd.Series(high) + pd.Series(low) + pd.Series(close)) / 3
    sma_tp = tp.rolling(n).mean()
    mad = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return ((tp - sma_tp) / (0.015 * mad.replace(0, np.nan))).to_numpy()


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.ADX(high, low, close, timeperiod=n)
    _mark_python_engine()
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    up_move = h.diff()
    down_move = -l.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    prev_close = c.shift(1)
    tr = pd.concat([h - l, (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    if HAS_TALIB:
        return _talib.OBV(close, volume)
    _mark_python_engine()
    direction = np.sign(pd.Series(close).diff()).fillna(0)
    return (direction * pd.Series(volume)).cumsum().to_numpy()


def _mom(close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.MOM(close, timeperiod=n)
    _mark_python_engine()
    s = pd.Series(close)
    return (s - s.shift(n)).to_numpy()


def _willr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    if HAS_TALIB:
        return _talib.WILLR(high, low, close, timeperiod=n)
    _mark_python_engine()
    highest_high = pd.Series(high).rolling(n).max()
    lowest_low = pd.Series(low).rolling(n).min()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    return (-100 * (highest_high - pd.Series(close)) / denom).to_numpy()
