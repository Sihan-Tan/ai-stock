"""desk_ai tools 白名单与 dispatch 测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401


@pytest.fixture()
def db_session():
    """内存库 Session，供 dispatch_tool 使用。"""
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


def test_dispatch_unknown_tool(db_session):
    """未知工具名应返回 error。"""
    from desk_ai.tools import dispatch_tool

    assert dispatch_tool(db_session, "place_order", {})["error"].startswith("unknown")


def test_dispatch_get_financials(db_session, monkeypatch):
    """get_financials 走 FinancialService。"""
    monkeypatch.setattr(
        "desk_market.financials.FinancialService.get_financials",
        lambda self, symbol, years=5: {"symbol": symbol, "source": "qmt", "metrics": []},
    )
    from desk_ai.tools import dispatch_tool

    out = dispatch_tool(db_session, "get_financials", {"symbol": "600519"})
    assert out["source"] == "qmt"
