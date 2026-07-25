from __future__ import annotations

import pandas as pd
import pytest

from desk_common.contracts import Side
from desk_strategy.factor_rules import eval_factor_rules, get_rule_params


def _hist(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": [10.0] * n,
            "high": [11.0] * n,
            "low": [9.0] * n,
            "close": [10.0 + i * 0.1 for i in range(n)],
            "volume": [1e6] * n,
        }
    )


def test_get_rule_params_defaults():
    assert get_rule_params({}) == {"position_pct": None, "max_hold_bars": 0}
    assert get_rule_params({"params": {"position_pct": 50, "max_hold_bars": 5}})["position_pct"] == 50.0
    assert get_rule_params({"params": {"position_pct": 50, "max_hold_bars": 5}})["max_hold_bars"] == 5


def test_max_hold_forces_sell():
    data = {
        "kind": "factor_rules",
        "params": {"max_hold_bars": 2},
        "buy": {"combine": "all", "conditions": []},
        "sell": {"combine": "any", "conditions": []},
    }
    hist = _hist(5)
    # Need eval to run with enough history; empty conditions means no buy/sell from rules.
    # max_hold should still add SELL when bars_held >= 2
    ctx = {"row": {"symbol": "600519.SH"}, "history": hist, "bars_held": 2}
    sigs = eval_factor_rules(data, ctx)
    assert any(getattr(s.side, "value", s.side) == "sell" or s.side == Side.SELL for s in sigs)
