"""股票搜索 API 与匹配逻辑。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import SecurityMeta
from desk_market.stock_search import name_pinyin_keys, search_securities


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


def _seed():
    db = get_session_factory()()
    db.add(SecurityMeta(symbol="600519.SH", name="贵州茅台", is_delisted=False, status="listed"))
    db.add(SecurityMeta(symbol="000596.SZ", name="古井贡酒", is_delisted=False, status="listed"))
    db.add(SecurityMeta(symbol="600000.SH", name="浦发银行", is_delisted=False, status="listed"))
    db.add(SecurityMeta(symbol="999999.SH", name="退市茅台", is_delisted=True, status="delisted"))
    db.commit()
    db.close()


def test_name_pinyin_keys_maotai():
    full, initials = name_pinyin_keys("贵州茅台")
    assert "guizhou" in full or full.startswith("gui")
    assert initials.startswith("gz") or "gzmt" in initials or initials == "gzmt"


def test_search_by_name_pinyin_code(client, _db):
    _seed()

    by_name = client.get("/api/market/stock/search", params={"q": "贵州"})
    assert by_name.status_code == 200
    items = by_name.json()["items"]
    assert any(i["symbol"] == "600519.SH" for i in items)
    assert len(items) <= 6

    by_py = client.get("/api/market/stock/search", params={"q": "gzmt"})
    assert by_py.status_code == 200
    assert any(i["symbol"] == "600519.SH" for i in by_py.json()["items"])

    by_code = client.get("/api/market/stock/search", params={"q": "600519"})
    assert by_code.status_code == 200
    assert by_code.json()["items"][0]["symbol"] == "600519.SH"

    empty = client.get("/api/market/stock/search", params={"q": ""})
    assert empty.json()["items"] == []


def test_search_excludes_delisted_and_default_limit(_db):
    _seed()
    db = get_session_factory()()
    for i in range(10):
        db.add(
            SecurityMeta(
                symbol=f"60100{i}.SH",
                name=f"贵州测试{i}",
                is_delisted=False,
                status="listed",
            )
        )
    db.commit()
    items = search_securities(db, "贵州", limit=6)
    db.close()
    assert len(items) == 6
    assert all(i["symbol"] != "999999.SH" for i in items)
