"""get_candlestick_patterns 与别名解析测试。"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

from desk_ai.candlestick_patterns import (
    get_candlestick_patterns,
    list_cdl_factor_names,
    resolve_pattern_names,
)
from desk_ai.tools import dispatch_tool


@pytest.fixture()
def db_session():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    db = Session(get_engine())
    try:
        yield db
    finally:
        db.close()
        reset_engine()
        get_settings.cache_clear()


def test_list_cdl_factor_names_nonempty():
    names = list_cdl_factor_names()
    assert "CDLENGULFING" in names
    assert "CDLMORNINGSTAR" in names
    assert len(names) >= 50


def test_resolve_patterns_aliases():
    resolved, unknown = resolve_pattern_names(["吞没", "ENGULFING", "CDLMORNINGSTAR", "不是形态"])
    assert "CDLENGULFING" in resolved
    assert "CDLMORNINGSTAR" in resolved
    assert resolved.count("CDLENGULFING") == 1
    assert "不是形态" in unknown


def test_resolve_patterns_all_when_empty():
    resolved, unknown = resolve_pattern_names(None)
    assert unknown == []
    assert len(resolved) == len(list_cdl_factor_names())


def test_get_candlestick_patterns_no_talib(monkeypatch):
    import desk_indicators

    monkeypatch.setattr(desk_indicators, "HAS_TALIB", False)
    out = get_candlestick_patterns(SimpleNamespace(), "600519")
    assert "error" in out
    assert "TA-Lib" in out["error"]


def test_get_candlestick_patterns_hits(monkeypatch):
    import desk_indicators

    monkeypatch.setattr(desk_indicators, "HAS_TALIB", True)

    class FakeFS:
        def __init__(self, db):
            pass

        def compute_series(self, symbol, names, start=None, end=None):
            return {
                "engine": "talib",
                "bars": [{"date": f"2026-07-{i:02d}"} for i in range(1, 11)],
                "series": {
                    "CDLENGULFING": {
                        "outputs": {
                            "cdlengulfing": [
                                {"date": "2026-07-09", "v": 0.0},
                                {"date": "2026-07-10", "v": 100.0},
                            ]
                        }
                    }
                },
            }

    monkeypatch.setattr("desk_factor.FactorService", FakeFS)
    out = get_candlestick_patterns(
        SimpleNamespace(),
        "600519",
        lookback_bars=10,
        patterns=["吞没"],
        only_hits=True,
    )
    assert out.get("error") is None
    assert out["hit_count"] == 1
    assert out["hits"][0]["name"] == "CDLENGULFING"
    assert out["hits"][0]["value"] == 100
    assert "吞没" in out["hits"][0]["name_zh"]


def test_dispatch_get_candlestick_patterns(db_session, monkeypatch):
    import desk_indicators

    monkeypatch.setattr(desk_indicators, "HAS_TALIB", True)

    class FakeFS:
        def __init__(self, db):
            pass

        def compute_series(self, symbol, names, start=None, end=None):
            return {
                "engine": "talib",
                "bars": [{"date": "2026-07-10"}],
                "series": {
                    "CDLDOJI": {
                        "outputs": {"cdldoji": [{"date": "2026-07-10", "v": -100.0}]}
                    }
                },
            }

    monkeypatch.setattr("desk_factor.FactorService", FakeFS)
    out = dispatch_tool(
        db_session,
        "get_candlestick_patterns",
        {"symbol": "600519", "patterns": ["CDLDOJI"], "lookback_bars": 5},
    )
    assert out["hits"][0]["name"] == "CDLDOJI"
    assert out["hits"][0]["value"] == -100
