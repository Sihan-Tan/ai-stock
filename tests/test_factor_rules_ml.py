"""factor_rules + ml: 因子。"""

from __future__ import annotations

import pandas as pd
import pytest

from desk_common.contracts import Side
from desk_strategy.factor_rules import (
    attach_ml_factor_columns,
    eval_factor_rules,
    _primary_output,
)

def _ohlcv(n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        c = 10.0 + i * 0.1
        rows.append(
            {
                "date": f"2024-01-{i + 1:02d}" if i < 28 else f"2024-02-{i - 27:02d}",
                "open": c,
                "high": c * 1.01,
                "low": c * 0.99,
                "close": c,
                "volume": 1_000_000.0,
            }
        )
    return pd.DataFrame(rows)


def test_primary_output_ml_is_factor_name():
    assert _primary_output("ml:demo") == "ml:demo"


def test_ml_compare_without_db_no_signal():
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "ml:demo"}, "right": {"const": 0.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv()})
    assert out == []


def test_ml_compare_with_precomputed_column_buys():
    hist = _ohlcv()
    hist["ml:demo"] = 0.2
    hist.loc[hist.index[-1], "ml:demo"] = 0.9
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "ml:demo"}, "right": {"const": 0.6}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1
    assert out[0].side == Side.BUY


def test_attach_ml_skips_when_column_present():
    hist = _ohlcv()
    hist["ml:demo"] = 0.55
    out = attach_ml_factor_columns(hist, ["ml:demo"], db=None)
    assert list(out["ml:demo"]) == list(hist["ml:demo"])


def test_yaml_on_bar_injects_db():
    """_yaml_on_bar 在 ctx 缺 db 时注入 registry.db。"""
    from unittest.mock import patch

    from desk_strategy import StrategyRegistry

    sentinel_db = object()
    reg = StrategyRegistry.__new__(StrategyRegistry)
    reg.db = sentinel_db
    data = {
        "kind": "factor_rules",
        "buy": {"combine": "all", "conditions": []},
        "sell": {"combine": "all", "conditions": []},
    }
    captured: dict = {}

    def _capture(_data, ctx):
        captured.update(ctx if isinstance(ctx, dict) else {})
        return []

    with patch("desk_strategy.factor_rules.eval_factor_rules", side_effect=_capture):
        reg._yaml_on_bar(data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv()})
    assert captured.get("db") is sentinel_db


@pytest.mark.skip(reason="Task 1 已覆盖预打分列；真实模型集成偏重，留给端到端")
def test_attach_ml_with_real_model():
    """可选：真实 as_factor 模型写入 ml: 列（需 DB + lightgbm）。"""
    raise AssertionError("skipped")
