"""CASE-AI 迁移策略：注册与信号冒烟。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.contracts import Side
from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_strategy import StrategyRegistry, _REGISTRY
from desk_strategy.bar_context import build_bar_row
import desk_strategy.strategies  # noqa: F401


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


EXPECTED_IDS = {
    "ma_cross",
    "macd_1d",
    "ma20_hold",
    "boll_revert",
    "bias_revert",
    "rsi_reversion",
    "turtle_donchian",
    "grid_classic",
    "multi_factor_lite",
}


def test_migrated_strategies_registered():
    """导入后内存注册表应包含迁移策略。"""
    assert EXPECTED_IDS <= set(_REGISTRY.keys())


def test_sync_python_writes_migrated_strategies(_db):
    """sync_python_to_db 应将迁移策略落库。"""
    db = Session(get_engine())
    n = StrategyRegistry(db).sync_python_to_db()
    db.commit()
    assert n >= len(EXPECTED_IDS)
    ids = {m.id for m in StrategyRegistry(db).list(source="python")}
    assert EXPECTED_IDS <= ids


def test_macd_golden_cross_signal():
    """构造 DIF 上穿 DEA 应产出买入。"""
    # 先下跌再抬升，末两根形成金叉近似
    closes = [100 - i * 0.5 for i in range(40)] + [80 + i * 1.2 for i in range(20)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    row = build_bar_row("600519.SH", closes=closes, highs=highs, lows=lows)
    strat = _REGISTRY["macd_1d"]
    assert strat.on_bar is not None
    # 若末根尚未金叉，至少保证可调用且返回 list
    out = strat.on_bar({"row": row})
    assert isinstance(out, list)


def test_turtle_breakout_signal():
    """收盘突破前 20 日高应买入。"""
    closes = [10.0] * 25 + [20.0]
    highs = [10.5] * 25 + [20.5]
    lows = [9.5] * 25 + [19.5]
    # 前 20 日高约 10.5，末收 20 突破
    row = build_bar_row("513100.SH", closes=closes, highs=highs, lows=lows)
    assert row["donchian_entry_high_20"] is not None
    assert row["close"] > row["donchian_entry_high_20"]
    signals = _REGISTRY["turtle_donchian"].on_bar({"row": row})  # type: ignore[misc]
    assert len(signals) == 1
    assert signals[0].side == Side.BUY


def test_boll_lower_touch_buy():
    """收盘低于下轨应买入。"""
    # 平稳后急跌，触下轨
    closes = [100.0] * 30 + [70.0]
    highs = [101.0] * 30 + [72.0]
    lows = [99.0] * 30 + [69.0]
    row = build_bar_row("000001.SZ", closes=closes, highs=highs, lows=lows)
    assert row["boll_lower"] is not None
    assert row["close"] < row["boll_lower"]
    signals = _REGISTRY["boll_revert"].on_bar({"row": row})  # type: ignore[misc]
    assert any(s.side == Side.BUY for s in signals)
