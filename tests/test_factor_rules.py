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


def test_near_pct_close_within_sma20():
    """收盘贴近预置 SMA_20 列 ±3% 时触发买。"""
    hist = _ohlcv([10.0] * 40)
    # 末根收盘 10.2，SMA_20=10 → 偏离 2% ≤ 3%
    hist.loc[hist.index[-1], "close"] = 10.2
    hist["sma_20"] = 10.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {
                    "op": "near_pct",
                    "left": {"factor": "CLOSE"},
                    "right": {"factor": "SMA_20"},
                    "pct": 3,
                },
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY


def test_near_pct_outside_band_no_signal():
    """偏离超过 pct 时不触发。"""
    hist = _ohlcv([10.0] * 40)
    hist.loc[hist.index[-1], "close"] = 11.0  # 10%
    hist["sma_20"] = 10.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {
                    "op": "near_pct",
                    "left": {"factor": "CLOSE"},
                    "right": {"factor": "SMA_20"},
                    "pct": 3,
                },
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    assert eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist}) == []


def test_sequence_same_day_two_steps():
    """sequence 允许同日两步；末步在今日（CLOSE 同时 >5 且 <20）。"""
    hist = _ohlcv([10.0] * 30)
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 5}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 20}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY


def test_sequence_gap_within_window():
    """条件1 在 T-3 真、条件2 在今日真，within_bars=5 → 买。"""
    hist = _ohlcv([10.0] * 30)
    # T-3: close=12（>11），其余日 close=10（不满足 >11）；今日 close=9（<9.5）
    hist.loc[hist.index[:-1], "close"] = 10.0
    hist.loc[hist.index[-4], "close"] = 12.0
    hist.loc[hist.index[-1], "close"] = 9.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY


def test_sequence_gap_exceeds_window_no_signal():
    """间隔超过 within_bars → 不触发。"""
    hist = _ohlcv([10.0] * 30)
    hist.loc[hist.index[:-1], "close"] = 10.0
    hist.loc[hist.index[-10], "close"] = 12.0  # 距今 9 根
    hist.loc[hist.index[-1], "close"] = 9.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    assert eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist}) == []


def test_sequence_last_step_not_today_no_signal():
    """末条件仅在昨日真、今日假 → 不触发。"""
    hist = _ohlcv([10.0] * 30)
    hist["close"] = 10.0
    hist.loc[hist.index[-2], "close"] = 9.0  # 昨日 < 9.5
    hist.loc[hist.index[-5], "close"] = 12.0
    # 今日 close=10：不满足 lt 9.5
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    assert eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist}) == []


def test_within_unordered_and_same_day():
    """within：两条件不同日或同日均可；无序。"""
    hist = _ohlcv([10.0] * 30)
    hist["close"] = 10.0
    hist.loc[hist.index[-3], "close"] = 12.0  # >11
    hist.loc[hist.index[-1], "close"] = 9.0  # <9.5；同窗
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "within",
            "within_bars": 5,
            "conditions": [
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY

    # 同日：gt 5 与 lt 20
    hist2 = _ohlcv([10.0] * 30)
    data2 = {
        "kind": "factor_rules",
        "buy": {
            "combine": "within",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 5}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 20}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out2 = eval_factor_rules(data2, {"row": {"symbol": "UT.SH"}, "history": hist2})
    assert len(out2) == 1 and out2[0].side == Side.BUY


def test_sequence_three_steps_needs_earlier_middle():
    """中间步有多个候选时须选较早 bar，贪心取最近会漏触发。"""
    hist = _ohlcv([7.0] * 11)
    hist["close"] = 7.0
    hist.loc[hist.index[6], "close"] = 101.0
    hist.loc[hist.index[8], "close"] = 50.0
    hist.loc[hist.index[9], "close"] = 50.0
    hist.loc[hist.index[10], "close"] = 5.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 2,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 100}},
                {"op": "eq", "left": {"factor": "CLOSE"}, "right": {"const": 50}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 8}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY


def test_combine_all_unchanged_regression():
    """all 仍只看当日：昨日曾 >11、今日 =10 不触发 gt 11。"""
    hist = _ohlcv([10.0] * 30)
    hist["close"] = 10.0
    hist.loc[hist.index[-2], "close"] = 12.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    assert eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist}) == []
