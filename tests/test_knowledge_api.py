"""知识库 REST API：CRUD、上传、检索。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch):
    """内存库 Session。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield Session(bind=get_engine())
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def api_client(db: Session):
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_docs_crud(api_client: TestClient):
    """POST 新建 → 列表 → 详情 → PUT → DELETE。"""
    created = api_client.post(
        "/api/knowledge/docs",
        json={"title": "笔记A", "content": "晋级率与情绪退潮观察", "tags": "情绪"},
    )
    assert created.status_code == 200
    doc_id = created.json()["doc_id"]

    listed = api_client.get("/api/knowledge/docs")
    assert listed.status_code == 200
    assert any(d["doc_id"] == doc_id for d in listed.json())

    detail = api_client.get(f"/api/knowledge/docs/{doc_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "笔记A"
    assert "晋级率" in body["content_preview"]

    updated = api_client.put(
        f"/api/knowledge/docs/{doc_id}",
        json={"title": "笔记B", "content": "更新后的正文内容", "tags": "复盘"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "笔记B"

    deleted = api_client.delete(f"/api/knowledge/docs/{doc_id}")
    assert deleted.status_code == 200
    missing = api_client.get(f"/api/knowledge/docs/{doc_id}")
    assert missing.status_code == 404


def test_upload_md(api_client: TestClient):
    """multipart 上传小 .md 文件。"""
    r = api_client.post(
        "/api/knowledge/docs/upload",
        files={"file": ("note.md", "# hello\n晋级率测试".encode("utf-8"), "text/markdown")},
        data={"tags": "上传"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["doc_id"]
    detail = api_client.get(f"/api/knowledge/docs/{body['doc_id']}")
    assert detail.status_code == 200
    assert "晋级率" in detail.json()["content_preview"]


def test_search_keyword(api_client: TestClient):
    """关键词检索返回命中。"""
    api_client.post(
        "/api/knowledge/docs",
        json={"title": "t", "content": "高位晋级率连续两日低于百分之三十则退潮", "tags": "情绪"},
    )
    hits = api_client.post(
        "/api/knowledge/search",
        json={"query": "晋级率", "top_k": 3, "mode": "keyword"},
    )
    assert hits.status_code == 200
    assert len(hits.json()) >= 1


def test_upload_invalid_extension(api_client: TestClient):
    """非法扩展名 → 400。"""
    r = api_client.post(
        "/api/knowledge/docs/upload",
        files={"file": ("x.docx", b"fake", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "pdf" in r.json()["detail"].lower() or "不支持" in r.json()["detail"]
