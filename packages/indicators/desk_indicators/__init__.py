"""技术指标：优先 TA-Lib abstract；不可用时对常用指标 pandas 降级。"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

try:
    import talib as _talib  # type: ignore
    from talib import abstract as _abstract

    HAS_TALIB = True
except Exception:  # pragma: no cover
    _talib = None
    _abstract = None
    HAS_TALIB = False

_LAST_ENGINE: str = "python"

# 字符串 spec → (talib名, 参数, 输出列)
_SPEC_ALIASES: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "BOLL": ("BBANDS", {"timeperiod": 20, "nbdevup": 2.0, "nbdevdn": 2.0}, ["boll_upper", "boll_mid", "boll_lower"]),
    "MACD": ("MACD", {}, ["macd", "macd_signal", "macd_hist"]),
    "STOCH": ("STOCH", {}, ["stoch_k", "stoch_d"]),
    "STOCHF": ("STOCHF", {}, ["stochf_k", "stochf_d"]),
    "OBV": ("OBV", {}, ["obv"]),
    "SAR": ("SAR", {}, ["sar"]),
    "APO": ("APO", {}, ["apo"]),
    "PPO": ("PPO", {}, ["ppo"]),
    "ULTOSC": ("ULTOSC", {}, ["ultosc"]),
    "BOP": ("BOP", {}, ["bop"]),
    "TRANGE": ("TRANGE", {}, ["trange"]),
    "AD": ("AD", {}, ["ad"]),
    "ADOSC": ("ADOSC", {}, ["adosc"]),
}

_OUTPUT_RENAME: dict[str, list[str]] = {
    "BBANDS": ["boll_upper", "boll_mid", "boll_lower"],
    "MACD": ["macd", "macd_signal", "macd_hist"],
    "MACDEXT": ["macd", "macd_signal", "macd_hist"],
    "MACDFIX": ["macd", "macd_signal", "macd_hist"],
    "STOCH": ["stoch_k", "stoch_d"],
    "STOCHF": ["stochf_k", "stochf_d"],
    "STOCHRSI": ["stochrsi_k", "stochrsi_d"],
    "AROON": ["aroon_down", "aroon_up"],
    "HT_SINE": ["ht_sine", "ht_leadsine"],
    "HT_PHASOR": ["ht_inphase", "ht_quadrature"],
    "MAMA": ["mama", "fama"],
    "MINMAX": ["minmax_min", "minmax_max"],
    "MINMAXINDEX": ["minmaxindex_min", "minmaxindex_max"],
}


def last_engine() -> str:
    """返回最近一次 compute 使用的计算引擎。"""
    return _LAST_ENGINE


def _mark_python_engine() -> None:
    global _LAST_ENGINE
    _LAST_ENGINE = "python"


def _parse_period_alias(key: str) -> tuple[str, dict[str, Any], list[str]] | None:
    """解析 SMA_20 / RSI_14 等周期别名。"""
    prefixes = (
        "SMA_", "EMA_", "WMA_", "DEMA_", "TEMA_", "KAMA_", "T3_", "TRIMA_", "MA_",
        "RSI_", "CCI_", "ATR_", "NATR_", "ADX_", "ADXR_", "DX_", "MOM_", "WILLR_",
        "ROC_", "ROCP_", "ROCR_", "CMO_", "MFI_", "TRIX_", "AROONOSC_",
        "PLUS_DI_", "MINUS_DI_", "PLUS_DM_", "MINUS_DM_",
    )
    for p in prefixes:
        if key.startswith(p):
            rest = key[len(p) :]
            if rest.isdigit():
                n = int(rest)
                talib_name = p[:-1]
                return talib_name, {"timeperiod": n}, [key.lower()]
    if key.startswith("AROON_") and key != "AROON_":
        rest = key.split("_", 1)[1]
        if rest.isdigit():
            n = int(rest)
            return "AROON", {"timeperiod": n}, ["aroon_down", "aroon_up"]
    return None


def resolve_spec(spec: str) -> tuple[str, dict[str, Any], list[str]]:
    """
    将注册名解析为 (talib函数名, 参数, 输出列名)。

    @raises ValueError: 无法识别
    """
    key = spec.upper()
    if key in _SPEC_ALIASES:
        return _SPEC_ALIASES[key]
    parsed = _parse_period_alias(key)
    if parsed:
        return parsed
    # 假定为正名
    outs = _OUTPUT_RENAME.get(key)
    if outs is None:
        outs = [key.lower()]
    return key, {}, outs


def apply_factor_specs(
    ohlcv: pd.DataFrame,
    specs: list[dict[str, Any]],
) -> pd.DataFrame:
    """
    按因子元数据批量计算。

    @param specs: 每项含 talib / params / outputs
    """
    global _LAST_ENGINE
    _LAST_ENGINE = "talib" if HAS_TALIB else "python"
    df = ohlcv.copy()
    for item in specs:
        talib_name = str(item["talib"]).upper()
        params = dict(item.get("params") or {})
        outputs = list(item["outputs"])
        _apply_one(df, talib_name, params, outputs)
    return df


def compute(ohlcv: pd.DataFrame, specs: Iterable[str] | None = None) -> pd.DataFrame:
    """
    计算技术指标。

    @param ohlcv: OHLCV DataFrame
    @param specs: 指标名列表
    """
    global _LAST_ENGINE
    _LAST_ENGINE = "talib" if HAS_TALIB else "python"
    df = ohlcv.copy()
    names = list(specs or ["SMA_5", "SMA_20", "EMA_12", "RSI_14", "MACD", "ATR_14", "BOLL"])
    for spec in names:
        talib_name, params, outputs = resolve_spec(spec)
        _apply_one(df, talib_name, params, outputs)
    return df


def _apply_one(
    df: pd.DataFrame,
    talib_name: str,
    params: dict[str, Any],
    outputs: list[str],
) -> None:
    if HAS_TALIB:
        try:
            _apply_talib_abstract(df, talib_name, params, outputs)
            return
        except Exception:
            # MAVP 等特殊输入失败时尝试降级
            pass
    _apply_python_fallback(df, talib_name, params, outputs)


def _price_frame(df: pd.DataFrame) -> pd.DataFrame:
    cols = {}
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            cols[c] = df[c].astype(float)
    frame = pd.DataFrame(cols)
    # BETA/CORREL 默认用 high/low
    if "high" in frame.columns:
        frame["price0"] = frame["high"]
    if "low" in frame.columns:
        frame["price1"] = frame["low"]
    # MAVP 需要 periods 序列：用常数 30
    if "close" in frame.columns:
        frame["periods"] = np.full(len(frame), 30.0)
    return frame


def _apply_talib_abstract(
    df: pd.DataFrame,
    talib_name: str,
    params: dict[str, Any],
    outputs: list[str],
) -> None:
    assert _abstract is not None
    fn = _abstract.Function(talib_name)
    # 过滤非法参数键
    valid = {k: params[k] for k in params if k in fn.parameters}
    # 补默认
    for k, v in fn.parameters.items():
        valid.setdefault(k, v)
    inputs = _price_frame(df)
    result = fn(inputs, **valid)
    _assign_outputs(df, result, outputs, talib_name)


def _assign_outputs(df: pd.DataFrame, result: Any, outputs: list[str], talib_name: str) -> None:
    if isinstance(result, pd.Series):
        if len(outputs) != 1:
            raise ValueError(f"{talib_name} expected {len(outputs)} outputs, got 1 series")
        df[outputs[0]] = result.astype(float).to_numpy()
        return
    if isinstance(result, pd.DataFrame):
        cols = list(result.columns)
        if len(outputs) != len(cols):
            # 按位置映射
            if len(outputs) == 1 and len(cols) == 1:
                df[outputs[0]] = result.iloc[:, 0].astype(float).to_numpy()
                return
            raise ValueError(f"{talib_name} output mismatch: {cols} vs {outputs}")
        for out, col in zip(outputs, cols, strict=True):
            df[out] = result[col].astype(float).to_numpy()
        return
    # ndarray / tuple
    if isinstance(result, tuple):
        if len(result) != len(outputs):
            raise ValueError(f"{talib_name} tuple size mismatch")
        for out, arr in zip(outputs, result, strict=True):
            df[out] = np.asarray(arr, dtype=float)
        return
    arr = np.asarray(result, dtype=float)
    if arr.ndim == 1:
        df[outputs[0]] = arr
        return
    raise ValueError(f"{talib_name}: unsupported result type {type(result)}")


def _apply_python_fallback(
    df: pd.DataFrame,
    talib_name: str,
    params: dict[str, Any],
    outputs: list[str],
) -> None:
    """无 TA-Lib 或 abstract 失败时的有限降级。"""
    _mark_python_engine()
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else close
    low = df["low"].astype(float) if "low" in df.columns else close
    open_ = df["open"].astype(float) if "open" in df.columns else close
    volume = df["volume"].astype(float) if "volume" in df.columns else None
    n = int(params.get("timeperiod", 14) or 14)
    name = talib_name.upper()

    if name == "SMA":
        df[outputs[0]] = close.rolling(n).mean().to_numpy()
    elif name == "EMA" or name == "MA" or name == "KAMA" or name == "T3" or name == "TRIMA":
        df[outputs[0]] = close.ewm(span=n, adjust=False).mean().to_numpy()
    elif name == "WMA":
        weights = np.arange(1, n + 1, dtype=float)
        df[outputs[0]] = (
            close.rolling(n).apply(lambda x: float(np.dot(x, weights) / weights.sum()), raw=True).to_numpy()
        )
    elif name == "DEMA":
        e1 = close.ewm(span=n, adjust=False).mean()
        e2 = e1.ewm(span=n, adjust=False).mean()
        df[outputs[0]] = (2 * e1 - e2).to_numpy()
    elif name == "TEMA":
        e1 = close.ewm(span=n, adjust=False).mean()
        e2 = e1.ewm(span=n, adjust=False).mean()
        e3 = e2.ewm(span=n, adjust=False).mean()
        df[outputs[0]] = (3 * e1 - 3 * e2 + e3).to_numpy()
    elif name == "RSI":
        delta = close.diff()
        up = delta.clip(lower=0).rolling(n).mean()
        down = (-delta.clip(upper=0)).rolling(n).mean()
        rs = up / down.replace(0, np.nan)
        df[outputs[0]] = (100 - (100 / (1 + rs))).to_numpy()
    elif name == "MOM":
        df[outputs[0]] = (close - close.shift(n)).to_numpy()
    elif name in ("ROC", "ROCR100"):
        df[outputs[0]] = (100 * (close - close.shift(n)) / close.shift(n).replace(0, np.nan)).to_numpy()
    elif name == "ROCP":
        df[outputs[0]] = ((close - close.shift(n)) / close.shift(n).replace(0, np.nan)).to_numpy()
    elif name == "ROCR":
        df[outputs[0]] = (close / close.shift(n).replace(0, np.nan)).to_numpy()
    elif name == "OBV":
        if volume is None:
            raise ValueError("OBV requires volume")
        direction = np.sign(close.diff()).fillna(0)
        df[outputs[0]] = (direction * volume).cumsum().to_numpy()
    elif name == "BBANDS":
        mid = close.rolling(n).mean()
        std = close.rolling(n).std()
        k = float(params.get("nbdevup", 2) or 2)
        df[outputs[0]] = (mid + k * std).to_numpy()
        df[outputs[1]] = mid.to_numpy()
        df[outputs[2]] = (mid - k * std).to_numpy()
    elif name == "MACD":
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df[outputs[0]] = macd.to_numpy()
        df[outputs[1]] = signal.to_numpy()
        df[outputs[2]] = (macd - signal).to_numpy()
    elif name == "ATR":
        prev = close.shift(1)
        tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
        df[outputs[0]] = tr.rolling(n).mean().to_numpy()
    elif name == "STOCH":
        fastk = int(params.get("fastk_period", 5) or 5)
        slowk = int(params.get("slowk_period", 3) or 3)
        slowd = int(params.get("slowd_period", 3) or 3)
        lowest_low = low.rolling(fastk).min()
        highest_high = high.rolling(fastk).max()
        denom = (highest_high - lowest_low).replace(0, np.nan)
        k = 100 * (close - lowest_low) / denom
        sk = k.rolling(slowk).mean()
        sd = sk.rolling(slowd).mean()
        df[outputs[0]] = sk.to_numpy()
        df[outputs[1]] = sd.to_numpy()
    elif name.startswith("CDL"):
        # 形态：无 TA-Lib 时填 0
        df[outputs[0]] = np.zeros(len(df))
    else:
        raise ValueError(f"unknown indicator or TA-Lib required: {talib_name}")
