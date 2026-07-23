"""factor_rules + ml: 因子。"""

from __future__ import annotations

import pandas as pd

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
