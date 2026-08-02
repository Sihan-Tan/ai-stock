"""TALIB_ZH_GUIDE 覆盖率与三段式格式。"""

from __future__ import annotations

from desk_factor.zh_desc import TALIB_ZH_DESC
from desk_factor.zh_guide import TALIB_ZH_GUIDE, zh_guide_for_talib


def test_guide_covers_all_zh_desc_keys():
    missing = sorted(set(TALIB_ZH_DESC) - set(TALIB_ZH_GUIDE))
    assert missing == [], f"缺少详述: {missing}"


def test_guide_has_three_sections():
    for key, text in TALIB_ZH_GUIDE.items():
        assert "【含义】" in text, key
        assert "【怎么用】" in text, key
        assert "【注意点】" in text, key
        assert "【含义】" not in TALIB_ZH_DESC[key]


def test_zh_guide_fallback_unknown():
    # 未知键回退短名或原名，不得抛错
    out = zh_guide_for_talib("NOT_A_REAL_FACTOR_XYZ")
    assert isinstance(out, str) and out
