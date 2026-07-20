"""FactorRegistry 一期默认名单与字段。"""

from __future__ import annotations

from desk_factor.registry import FACTOR_REGISTRY, default_enabled_names


def test_default_enabled_names():
    assert set(default_enabled_names()) == {
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


def test_registry_has_required_fields_and_plots():
    by_name = {f["name"]: f for f in FACTOR_REGISTRY}
    assert by_name["SMA_20"]["plot"] == "overlay"
    assert by_name["RSI_14"]["plot"] == "panel"
    assert by_name["STOCH"]["label"]  # 展示可用「KD」
    for f in FACTOR_REGISTRY:
        assert f["enabled"] is True
        assert f["category"]
        assert isinstance(f["params"], dict)
        assert isinstance(f["outputs"], list) and f["outputs"]
        assert f["plot"] in ("overlay", "panel")


def test_extra_registered_but_disabled_by_default():
    """至少有一个非默认开的因子，供折叠分类展示。"""
    extras = [f for f in FACTOR_REGISTRY if not f["default_enabled"]]
    assert any(f["name"] == "SMA_10" for f in extras)
    assert any(f["name"] == "WILLR_14" for f in extras)
