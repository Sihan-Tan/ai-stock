"""TA-Lib 全量因子注册表（158 + 常用周期别名）。

优先从本机 ``talib.get_function_groups()`` 生成；不可用时回退静态 158 名列表。
另附 SMA_5 / RSI_14 等周期别名，便于一期默认勾选与主图叠加。
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

PlotKind = Literal["overlay", "panel"]


class FactorMeta(TypedDict):
    name: str
    label: str
    category: str
    params: dict[str, Any]
    outputs: list[str]
    plot: PlotKind
    default_enabled: bool
    enabled: bool
    # 对应的 TA-Lib 函数名（周期别名会指向真实函数）
    talib: str


# 分组 → 左栏分类 / 主副图
_GROUP_META: dict[str, tuple[str, PlotKind]] = {
    "Cycle Indicators": ("cycle", "panel"),
    "Math Operators": ("math", "panel"),
    "Math Transform": ("math", "panel"),
    "Momentum Indicators": ("momentum", "panel"),
    "Overlap Studies": ("overlap", "overlay"),
    "Pattern Recognition": ("pattern", "panel"),
    "Price Transform": ("price", "overlay"),
    "Statistic Functions": ("statistic", "panel"),
    "Volatility Indicators": ("volatility", "panel"),
    "Volume Indicators": ("volume", "panel"),
}

# 无 talib 时的静态函数表（与官方 158 一致）
_STATIC_GROUPS: dict[str, list[str]] = {
    "Cycle Indicators": ["HT_DCPERIOD", "HT_DCPHASE", "HT_PHASOR", "HT_SINE", "HT_TRENDMODE"],
    "Math Operators": [
        "ADD", "DIV", "MAX", "MAXINDEX", "MIN", "MININDEX", "MINMAX", "MINMAXINDEX", "MULT", "SUB", "SUM",
    ],
    "Math Transform": [
        "ACOS", "ASIN", "ATAN", "CEIL", "COS", "COSH", "EXP", "FLOOR", "LN", "LOG10",
        "SIN", "SINH", "SQRT", "TAN", "TANH",
    ],
    "Momentum Indicators": [
        "ADX", "ADXR", "APO", "AROON", "AROONOSC", "BOP", "CCI", "CMO", "DX", "MACD", "MACDEXT",
        "MACDFIX", "MFI", "MINUS_DI", "MINUS_DM", "MOM", "PLUS_DI", "PLUS_DM", "PPO", "ROC",
        "ROCP", "ROCR", "ROCR100", "RSI", "STOCH", "STOCHF", "STOCHRSI", "TRIX", "ULTOSC", "WILLR",
    ],
    "Overlap Studies": [
        "BBANDS", "DEMA", "EMA", "HT_TRENDLINE", "KAMA", "MA", "MAMA", "MAVP", "MIDPOINT", "MIDPRICE",
        "SAR", "SAREXT", "SMA", "T3", "TEMA", "TRIMA", "WMA",
    ],
    "Pattern Recognition": [
        "CDL2CROWS", "CDL3BLACKCROWS", "CDL3INSIDE", "CDL3LINESTRIKE", "CDL3OUTSIDE",
        "CDL3STARSINSOUTH", "CDL3WHITESOLDIERS", "CDLABANDONEDBABY", "CDLADVANCEBLOCK",
        "CDLBELTHOLD", "CDLBREAKAWAY", "CDLCLOSINGMARUBOZU", "CDLCONCEALBABYSWALL", "CDLCOUNTERATTACK",
        "CDLDARKCLOUDCOVER", "CDLDOJI", "CDLDOJISTAR", "CDLDRAGONFLYDOJI", "CDLENGULFING",
        "CDLEVENINGDOJISTAR", "CDLEVENINGSTAR", "CDLGAPSIDESIDEWHITE", "CDLGRAVESTONEDOJI",
        "CDLHAMMER", "CDLHANGINGMAN", "CDLHARAMI", "CDLHARAMICROSS", "CDLHIGHWAVE", "CDLHIKKAKE",
        "CDLHIKKAKEMOD", "CDLHOMINGPIGEON", "CDLIDENTICAL3CROWS", "CDLINNECK", "CDLINVERTEDHAMMER",
        "CDLKICKING", "CDLKICKINGBYLENGTH", "CDLLADDERBOTTOM", "CDLLONGLEGGEDDOJI", "CDLLONGLINE",
        "CDLMARUBOZU", "CDLMATCHINGLOW", "CDLMATHOLD", "CDLMORNINGDOJISTAR", "CDLMORNINGSTAR",
        "CDLONNECK", "CDLPIERCING", "CDLRICKSHAWMAN", "CDLRISEFALL3METHODS", "CDLSEPARATINGLINES",
        "CDLSHOOTINGSTAR", "CDLSHORTLINE", "CDLSPINNINGTOP", "CDLSTALLEDPATTERN", "CDLSTICKSANDWICH",
        "CDLTAKURI", "CDLTASUKIGAP", "CDLTHRUSTING", "CDLTRISTAR", "CDLUNIQUE3RIVER",
        "CDLUPSIDEGAP2CROWS", "CDLXSIDEGAP3METHODS",
    ],
    "Price Transform": ["AVGPRICE", "MEDPRICE", "TYPPRICE", "WCLPRICE"],
    "Statistic Functions": [
        "BETA", "CORREL", "LINEARREG", "LINEARREG_ANGLE", "LINEARREG_INTERCEPT",
        "LINEARREG_SLOPE", "STDDEV", "TSF", "VAR",
    ],
    "Volatility Indicators": ["ATR", "NATR", "TRANGE"],
    "Volume Indicators": ["AD", "ADOSC", "OBV"],
}

# 输出列名兼容旧前端（MACD / BOLL / STOCH / AROON）
_OUTPUT_ALIASES: dict[str, list[str]] = {
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

# 一期默认勾选（周期别名）
_DEFAULT_ALIAS_NAMES = {
    "SMA_5",
    "SMA_20",
    "SMA_60",
    "EMA_12",
    "EMA_26",
    "BOLL",
    "RSI_14",
    "MACD",
    "ATR_14",
    "STOCH",
    "CCI_14",
    "ADX_14",
    "OBV",
    "MOM_10",
}


def _f(
    name: str,
    *,
    talib: str,
    label: str | None = None,
    category: str,
    params: dict[str, Any] | None = None,
    outputs: list[str] | None = None,
    plot: PlotKind,
    default_enabled: bool = False,
) -> FactorMeta:
    return {
        "name": name,
        "label": label or name,
        "category": category,
        "params": params or {},
        "outputs": outputs or [name.lower()],
        "plot": plot,
        "default_enabled": default_enabled,
        "enabled": True,
        "talib": talib,
    }


def _outputs_for(talib_name: str, abstract_outs: list[str] | None = None) -> list[str]:
    if talib_name in _OUTPUT_ALIASES:
        return list(_OUTPUT_ALIASES[talib_name])
    if abstract_outs:
        if len(abstract_outs) == 1 and abstract_outs[0] in ("real", "integer"):
            return [talib_name.lower()]
        return [f"{talib_name.lower()}_{o}" for o in abstract_outs]
    return [talib_name.lower()]


def _load_groups() -> dict[str, list[str]]:
    try:
        import talib

        return {k: list(v) for k, v in talib.get_function_groups().items()}
    except Exception:
        return {k: list(v) for k, v in _STATIC_GROUPS.items()}


def _abstract_outputs(talib_name: str) -> list[str] | None:
    try:
        from talib import abstract

        return list(abstract.Function(talib_name).output_names)
    except Exception:
        return None


def _abstract_params(talib_name: str) -> dict[str, Any]:
    try:
        from talib import abstract

        return dict(abstract.Function(talib_name).parameters)
    except Exception:
        return {}


def _build_canonical() -> list[FactorMeta]:
    rows: list[FactorMeta] = []
    for group, names in _load_groups().items():
        category, plot = _GROUP_META.get(group, ("other", "panel"))
        for name in names:
            outs = _outputs_for(name, _abstract_outputs(name))
            rows.append(
                _f(
                    name,
                    talib=name,
                    category=category,
                    params=_abstract_params(name),
                    outputs=outs,
                    plot=plot,
                    default_enabled=False,
                )
            )
    rows.sort(key=lambda r: (r["category"], r["name"]))
    return rows


def _build_period_aliases() -> list[FactorMeta]:
    """常用周期别名：不占用 158 正名，额外挂到目录。"""
    aliases: list[FactorMeta] = []

    def add(
        name: str,
        talib: str,
        category: str,
        plot: PlotKind,
        params: dict[str, Any],
        outputs: list[str],
        *,
        label: str | None = None,
        default_enabled: bool = False,
    ) -> None:
        aliases.append(
            _f(
                name,
                talib=talib,
                label=label,
                category=category,
                params=params,
                outputs=outputs,
                plot=plot,
                default_enabled=default_enabled or name in _DEFAULT_ALIAS_NAMES,
            )
        )

    for n in (5, 10, 20, 30, 60, 120):
        add(
            f"SMA_{n}",
            "SMA",
            "overlap",
            "overlay",
            {"timeperiod": n},
            [f"sma_{n}"],
            default_enabled=f"SMA_{n}" in _DEFAULT_ALIAS_NAMES,
        )
    for n in (12, 26, 60):
        add(
            f"EMA_{n}",
            "EMA",
            "overlap",
            "overlay",
            {"timeperiod": n},
            [f"ema_{n}"],
            default_enabled=f"EMA_{n}" in _DEFAULT_ALIAS_NAMES,
        )
    add("BOLL", "BBANDS", "volatility", "overlay", {"timeperiod": 20, "nbdevup": 2, "nbdevdn": 2}, ["boll_upper", "boll_mid", "boll_lower"], default_enabled=True)
    for n in (6, 14, 24):
        add(f"RSI_{n}", "RSI", "momentum", "panel", {"timeperiod": n}, [f"rsi_{n}"], default_enabled=f"RSI_{n}" in _DEFAULT_ALIAS_NAMES)
    add("ATR_14", "ATR", "volatility", "panel", {"timeperiod": 14}, ["atr_14"], default_enabled=True)
    add("CCI_14", "CCI", "momentum", "panel", {"timeperiod": 14}, ["cci_14"], default_enabled=True)
    add("ADX_14", "ADX", "momentum", "panel", {"timeperiod": 14}, ["adx_14"], default_enabled=True)
    add("MOM_10", "MOM", "momentum", "panel", {"timeperiod": 10}, ["mom_10"], default_enabled=True)
    add("WILLR_14", "WILLR", "momentum", "panel", {"timeperiod": 14}, ["willr_14"])
    add("WMA_20", "WMA", "overlap", "overlay", {"timeperiod": 20}, ["wma_20"])
    add("DEMA_20", "DEMA", "overlap", "overlay", {"timeperiod": 20}, ["dema_20"])
    add("TEMA_20", "TEMA", "overlap", "overlay", {"timeperiod": 20}, ["tema_20"])
    # MACD / STOCH / OBV 与正名同名时由 canonical 覆盖 default；别名表不再重复 MACD/STOCH/OBV
    return aliases


def _merge_registry() -> list[FactorMeta]:
    by_name: dict[str, FactorMeta] = {}
    for row in _build_canonical():
        by_name[row["name"]] = row
    for row in _build_period_aliases():
        # 别名优先（覆盖同名时保留别名的 default_enabled / outputs）
        existing = by_name.get(row["name"])
        if existing is None:
            by_name[row["name"]] = row
            continue
        # 同名：合并 default_enabled，保留别名 outputs/params
        merged = dict(row)
        merged["default_enabled"] = bool(row["default_enabled"] or existing["default_enabled"])
        by_name[row["name"]] = merged  # type: ignore[assignment]
    # MACD/STOCH/OBV 正名也要 default_enabled
    for name in ("MACD", "STOCH", "OBV"):
        if name in by_name and name in _DEFAULT_ALIAS_NAMES:
            by_name[name] = {**by_name[name], "default_enabled": True}  # type: ignore[misc]
    return sorted(by_name.values(), key=lambda r: (r["category"], r["name"]))


FACTOR_REGISTRY: list[FactorMeta] = _merge_registry()


def default_enabled_names() -> list[str]:
    """一期默认勾选的因子 name 列表。"""
    return [f["name"] for f in FACTOR_REGISTRY if f["default_enabled"] and f["enabled"]]


def get_factor(name: str) -> FactorMeta | None:
    """按 name 查找（大小写不敏感）。"""
    key = name.upper()
    for f in FACTOR_REGISTRY:
        if f["name"].upper() == key:
            return f
    return None


def list_enabled_registry() -> list[FactorMeta]:
    """目录可见项。"""
    return [f for f in FACTOR_REGISTRY if f["enabled"]]


def talib_function_count() -> int:
    """注册表中的 TA-Lib 正名数量（不含仅别名）。"""
    return sum(1 for f in FACTOR_REGISTRY if f["name"] == f["talib"])
