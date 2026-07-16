"""Stock detail API contracts。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import BoardMember, SecurityMeta


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


def test_security_meta_and_boards_for_symbol(client, _db):
    db = get_session_factory()()
    db.add(SecurityMeta(symbol="600519.SH", name="贵州茅台", status="listed"))
    db.add(
        BoardMember(
            board_code="BK0001",
            board_name="白酒",
            board_type="sector",
            symbol="600519.SH",
            effective_from=date(2020, 1, 1),
        )
    )
    db.commit()
    db.close()

    r = client.get("/api/market/stock/600519.SH/meta")
    assert r.status_code == 200
    assert r.json()["name"] == "贵州茅台"

    b = client.get("/api/market/stock/600519.SH/boards")
    assert b.status_code == 200
    assert b.json()["boards"][0]["board_name"] == "白酒"

    missing = client.get("/api/market/stock/999999.SH/meta")
    assert missing.status_code == 404
