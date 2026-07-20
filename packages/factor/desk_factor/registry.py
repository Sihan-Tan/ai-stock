"""TA-Lib / 技术因子注册表。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class FactorMeta(TypedDict):
    name: str
    label: str
    category: str
    params: dict[str, Any]
    outputs: list[str]
    plot: Literal["overlay", "panel"]
    default_enabled: bool
    enabled: bool


def _f(
    name: str,
    *,
    label: str | None = None,
    category: str,
    params: dict[str, Any] | None = None,
    outputs: list[str] | None = None,
    plot: Literal["overlay", "panel"],
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
    }


FACTOR_REGISTRY: list[FactorMeta] = [
    _f("SMA_5", category="trend", params={"period": 5}, outputs=["sma_5"], plot="overlay", default_enabled=True),
    _f("SMA_10", category="trend", params={"period": 10}, outputs=["sma_10"], plot="overlay"),
    _f("SMA_20", category="trend", params={"period": 20}, outputs=["sma_20"], plot="overlay", default_enabled=True),
    _f("SMA_60", category="trend", params={"period": 60}, outputs=["sma_60"], plot="overlay", default_enabled=True),
    _f("EMA_12", category="trend", params={"period": 12}, outputs=["ema_12"], plot="overlay", default_enabled=True),
    _f("EMA_26", category="trend", params={"period": 26}, outputs=["ema_26"], plot="overlay", default_enabled=True),
    _f(
        "BOLL",
        category="volatility",
        params={"period": 20, "nbdev": 2},
        outputs=["boll_mid", "boll_upper", "boll_lower"],
        plot="overlay",
        default_enabled=True,
    ),
    _f("ADX_14", category="trend", params={"period": 14}, outputs=["adx_14"], plot="panel", default_enabled=True),
    _f("RSI_14", category="momentum", params={"period": 14}, outputs=["rsi_14"], plot="panel", default_enabled=True),
    _f(
        "MACD",
        category="momentum",
        params={"fast": 12, "slow": 26, "signal": 9},
        outputs=["macd", "macd_signal", "macd_hist"],
        plot="panel",
        default_enabled=True,
    ),
    _f(
        "STOCH",
        label="KD",
        category="momentum",
        params={"fastk": 5, "slowk": 3, "slowd": 3},
        outputs=["stoch_k", "stoch_d"],
        plot="panel",
        default_enabled=True,
    ),
    _f("CCI_14", category="momentum", params={"period": 14}, outputs=["cci_14"], plot="panel", default_enabled=True),
    _f("MOM_10", category="momentum", params={"period": 10}, outputs=["mom_10"], plot="panel", default_enabled=True),
    _f("WILLR_14", category="momentum", params={"period": 14}, outputs=["willr_14"], plot="panel"),
    _f("ATR_14", category="volatility", params={"period": 14}, outputs=["atr_14"], plot="panel", default_enabled=True),
    _f("OBV", category="volume", outputs=["obv"], plot="panel", default_enabled=True),
]


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
