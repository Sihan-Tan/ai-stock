"""rule_optimize：预填、网格上限、选优与阈值改写。"""

from __future__ import annotations

import pytest

from desk_strategy.rule_optimize import (
    apply_threshold_params,
    build_prefill_doc,
    count_grid,
    has_optimizable_const_compares,
    pick_best_result,
    validate_grid,
)


def test_prefill_ml_and_rsi():
    doc = build_prefill_doc(["ml:demo", "RSI_14"])
    assert doc["kind"] == "factor_rules"
    assert doc["params"]["position_pct"] == 100
    assert doc["params"]["max_hold_bars"] == 0
    assert doc["buy"]["combine"] == "all"
    assert doc["sell"]["combine"] == "any"
    assert any(
        c.get("op") == "gt" and c["right"].get("const") == 0.6 for c in doc["buy"]["conditions"]
    )
    assert any(
        c.get("op") == "lt" and c["right"].get("const") == 30 for c in doc["buy"]["conditions"]
    )


def test_prefill_ma_uses_close_cross():
    doc = build_prefill_doc(["SMA_20"])
    buy = doc["buy"]["conditions"][0]
    sell = doc["sell"]["conditions"][0]
    assert buy["op"] == "cross_up"
    assert buy["left"]["factor"] == "CLOSE"
    assert buy["right"]["factor"] == "SMA_20"
    assert sell["op"] == "cross_down"
    assert sell["left"]["factor"] == "CLOSE"
    assert sell["right"]["factor"] == "SMA_20"


def test_prefill_other_ta_cross_sma20():
    """非均线 TA：factor cross_up SMA_20。"""
    doc = build_prefill_doc(["ATR_14"])
    buy = doc["buy"]["conditions"][0]
    assert buy["op"] == "cross_up"
    assert buy["left"]["factor"] == "ATR_14"
    assert buy["right"]["factor"] == "SMA_20"


def test_grid_cap():
    assert count_grid([0.5, 0.6], [0.3, 0.4], [50, 100], [0, 5, 10, 20]) == 32
    with pytest.raises(ValueError, match="200"):
        validate_grid(list(range(10)), list(range(10)), [50, 100], [0, 5, 10])  # 10*10*2*3=600


def test_count_grid_missing_side_is_one():
    assert count_grid([], [0.3, 0.4], [50], [0]) == 2
    assert count_grid(None, None, [50, 100], [0, 5]) == 4


def test_pick_best_prefers_return_then_dd():
    best = pick_best_result(
        [
            {"metrics": {"total_return": 0.1, "max_drawdown": -0.2}, "key": "a"},
            {"metrics": {"total_return": 0.1, "max_drawdown": -0.1}, "key": "b"},
            {"metrics": {"total_return": 0.05, "max_drawdown": -0.01}, "key": "c"},
        ]
    )
    assert best["key"] == "b"


def test_apply_threshold_params_updates_const_and_params():
    doc = build_prefill_doc(["ml:x"])
    out = apply_threshold_params(doc, buy_v=0.55, sell_v=0.35, position_pct=50, max_hold_bars=5)
    assert out["params"]["position_pct"] == 50
    assert out["params"]["max_hold_bars"] == 5
    assert out["buy"]["conditions"][0]["right"]["const"] == 0.55
    assert out["sell"]["conditions"][0]["right"]["const"] == 0.35
    assert out is not doc  # deep copy
    assert doc["buy"]["conditions"][0]["right"]["const"] == 0.6


def test_has_optimizable_const_compares_false_for_cross_only():
    doc = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {
                    "op": "cross_up",
                    "left": {"factor": "CLOSE"},
                    "right": {"factor": "SMA_20"},
                }
            ],
        },
        "sell": {
            "combine": "any",
            "conditions": [
                {
                    "op": "cross_down",
                    "left": {"factor": "CLOSE"},
                    "right": {"factor": "SMA_20"},
                }
            ],
        },
    }
    assert has_optimizable_const_compares(doc) is False


def test_has_optimizable_const_compares_true_for_ml():
    doc = build_prefill_doc(["ml:demo"])
    assert has_optimizable_const_compares(doc) is True
