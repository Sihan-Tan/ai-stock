"""BacktraderRunner 应读取 YAML params.position_pct 作为 sizer 比例。"""

from __future__ import annotations

from desk_backtest import resolve_sizer_percents


def test_resolve_sizer_percents():
    """position_pct 缺省 95；有值时钳制到 [1, 100]。"""
    assert resolve_sizer_percents({"params": {"position_pct": 50}}) == 50.0
    assert resolve_sizer_percents({}) == 95.0
    assert resolve_sizer_percents({"params": {"position_pct": 150}}) == 100.0
    assert resolve_sizer_percents({"params": {"position_pct": 0}}) == 1.0
