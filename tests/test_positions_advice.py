"""持仓建议：格式化、解析、编排。"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

from desk_positions_advice.format import append_advice_section
from desk_positions_advice.llm import normalize_action, parse_advice_payload


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    session = Session(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


def test_append_advice_section_empty_positions():
    base = "【尾盘选股】2026-07-27\n命中 1 只"
    advice = {
        "status": "empty",
        "source": "live",
        "section": "当前无持仓，跳过建议",
        "items": [],
    }
    out = append_advice_section(base, advice)
    assert "持仓建议（live）" in out
    assert "当前无持仓，跳过建议" in out
    assert out.startswith(base)


def test_normalize_action_closing_invalid():
    assert normalize_action("加仓", "closing") == ("持有", True)
    assert normalize_action("卖出", "closing") == ("卖出", False)


def test_normalize_action_morning():
    assert normalize_action("高抛低吸", "morning") == ("高抛低吸", False)
    assert normalize_action("低吸", "morning") == ("低吸", False)
    assert normalize_action("观望", "morning") == ("持有", True)
