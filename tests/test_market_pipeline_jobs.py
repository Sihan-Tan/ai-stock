"""任务运行记录与 QMT 断开可观测。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import MarketJobRun
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


class DeadMd(MockQmtMarketData):
    def get_daily_bars(self, *a, **k):
        raise RuntimeError("xtdata unavailable")


def test_job_records_failure_on_qmt_down(_db):
    db = Session(get_engine())
    jobs = MarketJobs(
        db,
        md=DeadMd(instruments=[InstrumentInfo("600519.SH", status="listed")]),
        akshare=None,
        config=None,
    )
    out = jobs.ingest_daily_incremental(asof=None)
    assert out["status"] == "failed"
    row = db.scalars(
        select(MarketJobRun).where(MarketJobRun.job_id == "ingest_daily_incremental")
    ).first()
    assert row is not None and row.status == "failed"
    blob = (row.error_summary or row.message or "").lower()
    assert "xtdata" in blob or "unavailable" in blob
