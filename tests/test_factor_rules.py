"""factor_rules 求值器单测。"""

from __future__ import annotations

import pandas as pd

from desk_common.contracts import Side
from desk_strategy.factor_rules import eval_factor_rules


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    """由收盘序列构造简单 OHLCV。"""
    rows = []
    for i, c in enumerate(closes):
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


def test_compare_lt_rsi_triggers_buy():
    """持续下跌使 RSI 偏低，RSI_14 < 80 应触发买（宽松阈值保证稳定）。"""
    # 足够长的下跌序列
    closes = [100.0 - i * 0.8 for i in range(80)]
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "lt", "left": {"factor": "RSI_14"}, "right": {"const": 80}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv(closes)})
    assert len(out) == 1
    assert out[0].side == Side.BUY


def test_cross_up_sma_triggers_buy():
    """前段下跌后快速拉升，SMA_5 上穿 SMA_20。"""
    closes = [100.0 - i * 0.5 for i in range(40)] + [80.0 + i * 2.5 for i in range(15)]
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {
                    "op": "cross_up",
                    "left": {"factor": "SMA_5"},
                    "right": {"factor": "SMA_20"},
                },
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    # 在整段历史上求值；若末 bar 已不是交叉日，向前找首个交叉日
    hist = _ohlcv(closes)
    hit = False
    for end in range(25, len(hist) + 1):
        out = eval_factor_rules(
            data, {"row": {"symbol": "UT.SH"}, "history": hist.iloc[:end].copy()}
        )
        if out and out[0].side == Side.BUY:
            hit = True
            break
    assert hit, "expected SMA_5 cross_up SMA_20 somewhere in series"


def test_sell_priority_when_both_true():
    """买卖条件皆恒真时仅卖。"""
    closes = [10.0 + (i % 3) for i in range(60)]
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "SMA_5"}, "right": {"const": 0}},
            ],
        },
        "sell": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "SMA_5"}, "right": {"const": 0}},
            ],
        },
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv(closes)})
    assert len(out) == 1
    assert out[0].side == Side.SELL


def test_combine_any_or():
    """OR：一真即触发。"""
    closes = [100.0 + i * 0.1 for i in range(50)]
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "any",
            "conditions": [
                {"op": "lt", "left": {"factor": "SMA_5"}, "right": {"const": -999}},
                {"op": "gt", "left": {"factor": "SMA_5"}, "right": {"const": 0}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv(closes)})
    assert len(out) == 1 and out[0].side == Side.BUY


def test_unknown_factor_is_false_not_raise():
    """未知因子不抛错，条件为假。"""
    closes = [10.0 + i for i in range(40)]
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "NO_SUCH_FACTOR"}, "right": {"const": 0}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv(closes)})
    assert out == []


def test_yaml_on_bar_dispatches_factor_rules():
    """StrategyRegistry._yaml_on_bar 识别 kind=factor_rules。"""
    from desk_strategy import StrategyRegistry

    closes = [100.0 - i * 0.8 for i in range(80)]
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "lt", "left": {"factor": "RSI_14"}, "right": {"const": 80}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    reg = StrategyRegistry.__new__(StrategyRegistry)
    reg.db = None
    out = reg._yaml_on_bar(
        data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv(closes)}
    )
    assert len(out) == 1 and out[0].side == Side.BUY
