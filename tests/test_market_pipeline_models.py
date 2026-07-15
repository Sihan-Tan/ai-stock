"""ORM 列与唯一键。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BarDaily, MarketJobRun, SecurityMeta


@pytest.fixture()
def _db():
    """SQLite 内存库 + create_all（与 test_core 一致）。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    reset_engine()
    get_settings.cache_clear()


def test_bar_daily_has_hfq_columns(_db):
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    assert hasattr(BarDaily, "open_hfq")
    assert hasattr(BarDaily, "close_hfq")
    assert hasattr(BarDaily, "volume_hfq")
    # 默认列无 _qfq 后缀
    assert not hasattr(BarDaily, "open_qfq")


def test_security_meta_and_job_run(_db):
    assert SecurityMeta.__tablename__ == "security_meta"
    assert MarketJobRun.__tablename__ == "market_job_runs"


def test_bars_daily_columns_present(_db):
    cols = set(BarDaily.__table__.c.keys())
    for name in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "open_hfq",
        "high_hfq",
        "low_hfq",
        "close_hfq",
        "volume_hfq",
        "adj_factor",
    ):
        assert name in cols
    assert "open_qfq" not in cols
    assert "uq_bars_daily_symbol_ts" in {
        c.name for c in BarDaily.__table__.constraints if hasattr(c, "name") and c.name
    }
