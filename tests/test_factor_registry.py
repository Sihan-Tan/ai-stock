"""FactorRegistry 全量 TA-Lib 与默认名单。"""

from __future__ import annotations

from desk_factor.registry import FACTOR_REGISTRY, default_enabled_names, talib_function_count


def test_talib_canonical_count_is_158():
    assert talib_function_count() == 158
    assert len(FACTOR_REGISTRY) >= 158


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
    assert by_name["STOCH"]["label"]
    assert by_name["CDLDOJI"]["category"] == "pattern"
    assert by_name["SMA"]["talib"] == "SMA"
    assert "相对强弱" in by_name["RSI_14"]["label"]
    assert "【含义】" in by_name["RSI_14"]["description"]
    assert "【怎么用】" in by_name["RSI_14"]["description"]
    assert "【含义】" not in by_name["RSI_14"]["label"]
    assert "简单移动平均" in by_name["SMA_20"]["label"]
    assert "【含义】" in by_name["SMA_20"]["description"]
    assert "本条目默认周期" in by_name["SMA_20"]["description"]
    assert "本条目默认周期" in by_name["RSI_14"]["description"]
    assert "【含义】" in by_name["CLOSE"]["description"]
    assert "【含义】" in by_name["CDLDOJI"]["description"]
    assert by_name["CLOSE"]["outputs"] == ["close"]
    assert by_name["CLOSE"]["category"] == "price"
    assert by_name["VOLUME"]["outputs"] == ["volume"]
    assert by_name["VOLUME"]["plot"] == "panel"
    for f in FACTOR_REGISTRY:
        assert f["enabled"] is True
        assert f["category"]
        assert isinstance(f["params"], dict)
        assert isinstance(f["outputs"], list) and f["outputs"]
        assert f["plot"] in ("overlay", "panel")
        assert "talib" in f
        assert isinstance(f.get("description"), str) and f["description"]


def test_extra_registered_but_disabled_by_default():
    extras = [f for f in FACTOR_REGISTRY if not f["default_enabled"]]
    assert len(extras) >= 140
    assert any(f["name"] == "SMA_10" for f in extras)
    assert any(f["name"] == "WILLR_14" for f in extras)
    assert any(f["name"] == "CDLENGULFING" for f in extras)
