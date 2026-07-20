"""扩展指标：abstract 全量路径与未知名。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from desk_indicators import HAS_TALIB, apply_factor_specs, compute


def _ohlcv(n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + 1
    low = close - 1
    open_ = close
    volume = rng.integers(1000, 5000, n).astype(float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def test_compute_extra_indicators_columns():
    df = compute(
        _ohlcv(),
        [
            "STOCH",
            "CCI_14",
            "ADX_14",
            "OBV",
            "MOM_10",
            "SMA_60",
            "EMA_26",
            "WILLR_14",
            "WMA_20",
            "MFI_14",
            "AROON_14",
            "SAR",
            "AD",
            "CDLDOJI",
            "AVGPRICE",
        ],
    )
    for col in (
        "stoch_k",
        "stoch_d",
        "cci_14",
        "adx_14",
        "obv",
        "mom_10",
        "sma_60",
        "ema_26",
        "willr_14",
        "wma_20",
        "mfi_14",
        "aroon_up",
        "aroon_down",
        "sar",
        "ad",
        "cdldoji",
        "avgprice",
    ):
        assert col in df.columns
        assert df[col].notna().sum() > 0 or col == "cdldoji"


def test_unknown_spec_raises():
    with pytest.raises(ValueError, match="unknown|TA-Lib required"):
        compute(_ohlcv(30), ["NOT_A_REAL_FACTOR"])


def test_engine_flag_matches_has_talib():
    from desk_indicators import last_engine

    compute(_ohlcv(40), ["SMA_5"])
    assert last_engine() in ("talib", "python")
    assert (last_engine() == "talib") == HAS_TALIB


def test_python_fallback_smoke(monkeypatch):
    import desk_indicators as ind

    monkeypatch.setattr(ind, "HAS_TALIB", False)
    df = ind.compute(_ohlcv(50), ["STOCH", "OBV", "MOM_10"])
    for col in ("stoch_k", "stoch_d", "obv", "mom_10"):
        assert col in df.columns
        assert df[col].notna().sum() > 0
    assert ind.last_engine() == "python"


def test_apply_factor_specs_canonical_rsi():
    df = apply_factor_specs(
        _ohlcv(60),
        [{"talib": "RSI", "params": {"timeperiod": 14}, "outputs": ["rsi"]}],
    )
    assert "rsi" in df.columns
    assert df["rsi"].notna().sum() > 0
