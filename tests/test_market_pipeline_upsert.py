"""日线 upsert 幂等：默认列 + _hfq。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BarDaily
from desk_market import MarketService


@pytest.fixture()
def _db():
    """SQLite 内存库 + create_all（与 test_market_pipeline_models 一致）。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    reset_engine()
    get_settings.cache_clear()


def _session() -> Session:
    engine = get_engine()
    return Session(engine)


def test_upsert_daily_bars_writes_hfq_and_is_idempotent(_db):
    db = _session()
    svc = MarketService(db)
    df = pd.DataFrame(
        [
            {
                "date": date(2024, 1, 2),
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000,
                "amount": 10500,
                "open_hfq": 100.0,
                "high_hfq": 110.0,
                "low_hfq": 95.0,
                "close_hfq": 105.0,
                "volume_hfq": 1000,
            }
        ]
    )
    assert svc.upsert_daily_bars("600519.SH", df) == 1
    db.commit()
    # 覆盖更新
    df2 = df.copy()
    df2["close"] = 10.8
    df2["close_hfq"] = 108.0
    assert svc.upsert_daily_bars("600519.SH", df2) == 1
    db.commit()
    n = db.scalar(select(func.count()).select_from(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert n == 1
    row = db.scalar(select(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert row.close == 10.8
    assert row.close_hfq == 108.0
    assert row.open == 10.0


def test_load_daily_df_adj_qfq_default_and_hfq(_db):
    db = _session()
    svc = MarketService(db)
    svc.upsert_daily_bars(
        "600519.SH",
        pd.DataFrame(
            [
                {
                    "date": date(2024, 1, 2),
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "volume": 1,
                    "amount": 1,
                    "open_hfq": 100.0,
                    "high_hfq": 110.0,
                    "low_hfq": 95.0,
                    "close_hfq": 105.0,
                    "volume_hfq": 1,
                }
            ]
        ),
    )
    db.commit()
    qfq = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 3), adj="qfq")
    assert float(qfq.iloc[0]["close"]) == 10.5
    hfq = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 3), adj="hfq")
    assert float(hfq.iloc[0]["close"]) == 105.0
    default = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 3))
    assert float(default.iloc[0]["close"]) == 10.5


def _full_bar_row() -> dict:
    """完整 OHLCV + *_hfq 行。"""
    return {
        "date": date(2024, 1, 2),
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": 10.5,
        "volume": 1000,
        "amount": 10500,
        "open_hfq": 100.0,
        "high_hfq": 110.0,
        "low_hfq": 95.0,
        "close_hfq": 105.0,
        "volume_hfq": 1000,
    }


def test_upsert_skips_incomplete_row_missing_hfq(_db):
    """缺 close_hfq 或仅 OHLCV 时跳过，返回 0 且不入库。"""
    db = _session()
    svc = MarketService(db)

    missing_hfq = _full_bar_row()
    del missing_hfq["close_hfq"]
    assert svc.upsert_daily_bars("600519.SH", pd.DataFrame([missing_hfq])) == 0
    db.commit()
    n = db.scalar(select(func.count()).select_from(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert n == 0

    ohlcv_only = {
        "date": date(2024, 1, 3),
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": 10.5,
        "volume": 1000,
        "amount": 10500,
    }
    assert svc.upsert_daily_bars("600519.SH", pd.DataFrame([ohlcv_only])) == 0
    db.commit()
    n = db.scalar(select(func.count()).select_from(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert n == 0


def test_upsert_incomplete_does_not_overwrite_existing_full_row(_db):
    """完整行已存在时，不完整 upsert 不修改已有值。"""
    db = _session()
    svc = MarketService(db)
    full = _full_bar_row()
    assert svc.upsert_daily_bars("600519.SH", pd.DataFrame([full])) == 1
    db.commit()

    incomplete = {
        "date": date(2024, 1, 2),
        "open": 99.0,
        "high": 99.0,
        "low": 99.0,
        "close": 99.0,
        "volume": 9999,
        "amount": 9999,
    }
    assert svc.upsert_daily_bars("600519.SH", pd.DataFrame([incomplete])) == 0
    db.commit()

    row = db.scalar(select(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert row.close == 10.5
    assert row.close_hfq == 105.0
    assert row.open == 10.0


def test_load_daily_df_adj_forward_matches_qfq_default(_db):
    """adj=forward 与 default/qfq 返回相同 close。"""
    db = _session()
    svc = MarketService(db)
    svc.upsert_daily_bars("600519.SH", pd.DataFrame([_full_bar_row()]))
    db.commit()

    start, end = date(2024, 1, 1), date(2024, 1, 3)
    qfq = svc.load_daily_df("600519.SH", start, end, adj="qfq")
    forward = svc.load_daily_df("600519.SH", start, end, adj="forward")
    default = svc.load_daily_df("600519.SH", start, end)

    assert float(forward.iloc[0]["close"]) == 10.5
    assert float(forward.iloc[0]["close"]) == float(qfq.iloc[0]["close"])
    assert float(forward.iloc[0]["close"]) == float(default.iloc[0]["close"])
