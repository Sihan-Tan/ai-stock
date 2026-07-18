"""回测 / 策略共用的 bar 上下文构造。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from desk_indicators import compute


def build_bar_row(
    symbol: str,
    *,
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    opens: list[float] | None = None,
    volumes: list[float] | None = None,
) -> dict[str, Any]:
    """
    由历史 OHLCV 序列构造策略 ``on_bar`` 所需行字典（含指标与前值）。

    @param symbol: 标的
    @param closes: 收盘价序列（时间升序，末项为当前 bar）
    @param highs: 最高价；缺省用 close
    @param lows: 最低价；缺省用 close
    @param opens: 开盘价；缺省用 close
    @param volumes: 成交量；缺省 0
    @returns: 供策略读取的 row
    """
    n = len(closes)
    if n == 0:
        return {"symbol": symbol}
    highs = highs if highs is not None else list(closes)
    lows = lows if lows is not None else list(closes)
    opens = opens if opens is not None else list(closes)
    volumes = volumes if volumes is not None else [0.0] * n

    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )
    df = compute(
        df,
        specs=[
            "SMA_5",
            "SMA_20",
            "EMA_5",
            "EMA_20",
            "RSI_14",
            "MACD",
            "BOLL",
        ],
    )
    cur = df.iloc[-1]
    prev = df.iloc[-2] if n >= 2 else cur

    def _f(series_row: pd.Series, key: str) -> float | None:
        value = series_row.get(key)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    close = float(cur["close"])
    high = float(cur["high"])
    low = float(cur["low"])
    prev_close = float(prev["close"])

    # 唐奇安：不含当日的过去 N 日高低
    entry_high_20 = None
    exit_low_10 = None
    if n >= 21:
        entry_high_20 = float(max(highs[-21:-1]))
    if n >= 11:
        exit_low_10 = float(min(lows[-11:-1]))

    high_60 = float(max(highs[-60:])) if n >= 60 else None
    low_60 = float(min(lows[-60:])) if n >= 60 else None

    mom_1m = None
    if n >= 22 and closes[-22] != 0:
        mom_1m = close / float(closes[-22]) - 1.0

    sma_20 = _f(cur, "sma_20")
    bias_20 = None
    if sma_20 is not None and sma_20 > 0:
        bias_20 = (close - sma_20) / sma_20

    return {
        "symbol": symbol,
        "open": float(cur["open"]),
        "high": high,
        "low": low,
        "close": close,
        "volume": float(cur["volume"]),
        "prev_close": prev_close,
        "sma_5": _f(cur, "sma_5"),
        "sma_20": sma_20,
        "prev_sma_5": _f(prev, "sma_5"),
        "prev_sma_20": _f(prev, "sma_20"),
        "ema_5": _f(cur, "ema_5"),
        "ema_20": _f(cur, "ema_20"),
        "prev_ema_5": _f(prev, "ema_5"),
        "prev_ema_20": _f(prev, "ema_20"),
        "rsi_14": _f(cur, "rsi_14"),
        "prev_rsi_14": _f(prev, "rsi_14"),
        "macd": _f(cur, "macd"),
        "macd_signal": _f(cur, "macd_signal"),
        "macd_hist": _f(cur, "macd_hist"),
        "prev_macd": _f(prev, "macd"),
        "prev_macd_signal": _f(prev, "macd_signal"),
        "boll_mid": _f(cur, "boll_mid"),
        "boll_upper": _f(cur, "boll_upper"),
        "boll_lower": _f(cur, "boll_lower"),
        "prev_boll_mid": _f(prev, "boll_mid"),
        "donchian_entry_high_20": entry_high_20,
        "donchian_exit_low_10": exit_low_10,
        "range_high_60": high_60,
        "range_low_60": low_60,
        "mom_1m": mom_1m,
        "bias_20": bias_20,
    }
