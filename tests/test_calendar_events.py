"""财经日历 / 重大新闻 / 催化剂。"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from desk_calendar import CalendarEventService, CalendarEventSync, SeedCalendarEventsClient
from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
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


@pytest.fixture()
def client(_db):
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_seed_sync_writes_today_and_horizon(_db):
    db = get_session_factory()()
    try:
        today = date.today()
        end = today + timedelta(days=90)
        n = CalendarEventSync(db, SeedCalendarEventsClient()).run(today, end)
        db.commit()
        assert n >= 10
        svc = CalendarEventService(db)
        majors = svc.list_today_major(today, min_importance=4)
        assert len(majors) >= 1
        assert any(item["category"] == "news" for item in majors)
        horizon = svc.list_events(today, end)
        cats = {item["category"] for item in horizon}
        assert "macro" in cats
        assert cats & {"catalyst", "earnings", "lockup", "ipo"}
    finally:
        db.close()


def test_events_api_today_and_range(client):
    seeded = client.post("/api/calendar/events/sync?months=3&prefer_seed=true")
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["synced"] >= 1

    today = client.get("/api/calendar/events/today")
    assert today.status_code == 200, today.text
    body = today.json()
    assert "items" in body
    assert len(body["items"]) >= 1

    horizon = client.get("/api/calendar/events?months=3")
    assert horizon.status_code == 200, horizon.text
    data = horizon.json()
    assert len(data["items"]) >= 5
    assert data["start"] <= data["end"]


def test_events_sync_endpoint(client):
    r = client.post("/api/calendar/events/sync?months=3&prefer_seed=true")
    assert r.status_code == 200, r.text
    assert r.json()["synced"] >= 1
    assert r.json()["source"] == "seed"
