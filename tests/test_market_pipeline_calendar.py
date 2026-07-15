"""日历同步与未同步提示。"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_calendar import CalendarService, CalendarSync
from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


class FakeAkCal:
    def trade_days(self, start: date, end: date) -> list[tuple[date, bool]]:
        return [
            (date(2024, 1, 1), False),
            (date(2024, 1, 2), True),
        ]


def test_calendar_sync_upserts(_db):
    db = Session(get_engine())
    n = CalendarSync(db, client=FakeAkCal()).run(date(2024, 1, 1), date(2024, 1, 2))
    assert n >= 2
    svc = CalendarService(db)
    assert svc.is_trade_day(date(2024, 1, 1)) is False
    assert svc.is_trade_day(date(2024, 1, 2)) is True


def test_is_trade_day_logs_when_calendar_missing(caplog, _db):
    db = Session(get_engine())
    svc = CalendarService(db)
    with caplog.at_level(logging.WARNING):
        assert svc.is_trade_day(date(2024, 5, 1)) is True
    assert any("日历未同步" in r.message for r in caplog.records)
