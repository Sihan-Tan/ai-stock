"""导出/导入核心行情表 CSV 的往返测试。"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BarDaily, QuoteSnapshot, TradeCalendar

# scripts 不在默认 pythonpath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from market_data_io import export_tables, import_tables  # noqa: E402


@pytest.fixture()
def db_engine(tmp_path: Path):
    """内存库 + 行情样例数据。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        db.add(
            BarDaily(
                symbol="600519",
                ts=date(2024, 1, 2),
                open=100,
                high=101,
                low=99,
                close=100.5,
                volume=1.0,
                amount=100.0,
            )
        )
        db.add(
            QuoteSnapshot(
                symbol="600519",
                name="贵州茅台",
                last=100.5,
                pct_chg=1.2,
                amount=1e8,
                updated_at=datetime(2024, 1, 2, 15, 0, 0),
            )
        )
        db.add(TradeCalendar(cal_date=date(2024, 1, 2), is_open=True, note=""))
        db.commit()
    yield engine
    reset_engine()
    get_settings.cache_clear()


def test_export_import_roundtrip(db_engine, tmp_path: Path):
    """导出 CSV 后再导入，行数与关键字段保留。"""
    out = tmp_path / "market"
    export_tables(db_engine, out)
    assert (out / "bars_daily.csv").exists()
    assert (out / "manifest.json").exists()

    with Session(db_engine) as db:
        db.query(BarDaily).delete()
        db.query(QuoteSnapshot).delete()
        db.query(TradeCalendar).delete()
        db.commit()
        assert db.query(BarDaily).count() == 0

    counts = import_tables(db_engine, out, clear=True)
    assert counts.get("bars_daily") == 1
    assert counts.get("quotes_snapshot") == 1
    assert counts.get("trade_calendar") == 1

    with Session(db_engine) as db:
        bar = db.query(BarDaily).one()
        assert bar.symbol == "600519"
        assert float(bar.close) == 100.5
        quote = db.query(QuoteSnapshot).one()
        assert quote.name == "贵州茅台"
