"""知识库切片、PDF 抽取与 KnowledgeStore CRUD。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

from desk_knowledge import KnowledgeStore
from desk_knowledge.chunking import chunk_text
from desk_knowledge.pdf_extract import extract_pdf_text


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch):
    """内存库 Session。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    get_settings.cache_clear()
    session = Session(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


def test_chunk_overlap():
    """重叠窗口：后一段开头等于前一段末尾 overlap 字。"""
    text = "字" * 1000
    parts = chunk_text(text, size=800, overlap=100)
    assert len(parts) >= 2
    assert len(parts[0]) == 800
    assert parts[0][-100:] == parts[1][:100]


def test_chunk_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_extract_pdf_empty_raises(tmp_path: Path):
    """无文字层 PDF 应抛出中文 ValueError。"""
    from pypdf import PdfWriter

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as f:
        writer.write(f)
    with pytest.raises(ValueError, match="无法抽取|OCR"):
        extract_pdf_text(path)


def test_upsert_and_update_rebuilds(db: Session, tmp_path: Path):
    store = KnowledgeStore(db, root=str(tmp_path))
    a = store.upsert("t", "hello " * 200, tags="a")
    b = store.update(a["doc_id"], title="t2", content="全新内容" * 100, tags="b")
    assert b["doc_id"] == a["doc_id"]
    assert len([d for d in store.list_docs() if d["doc_id"] == a["doc_id"]]) == 1
    g = store.get(a["doc_id"])
    assert g["title"] == "t2"
    assert g["chunk_count"] >= 1
    assert g["tags"] == "b"


def test_delete_removes(db: Session, tmp_path: Path):
    store = KnowledgeStore(db, root=str(tmp_path))
    a = store.upsert("x", "abc " * 50)
    path = Path(store.get(a["doc_id"])["path"])
    assert path.exists()
    store.delete(a["doc_id"])
    assert store.list_docs() == []
    assert not path.exists()


def test_list_docs_includes_chunk_count(db: Session, tmp_path: Path):
    store = KnowledgeStore(db, root=str(tmp_path))
    a = store.create("n", "内容" * 500)
    docs = store.list_docs()
    row = next(d for d in docs if d["doc_id"] == a["doc_id"])
    assert row["chunk_count"] >= 1


def test_get_preview_and_full(db: Session, tmp_path: Path):
    store = KnowledgeStore(db, root=str(tmp_path))
    body = "甲" * 25000
    a = store.create("big", body)
    g = store.get(a["doc_id"])
    assert g["content_truncated"] is True
    assert len(g["content_preview"]) == 20000
    assert "content" not in g or g.get("content") is None
    full = store.get(a["doc_id"], full=True)
    assert full["content"] == body
    assert full["content_truncated"] is True


def test_keyword_search_hits_chinese(db: Session, tmp_path: Path):
    """中文分词能命中切片，且结果带 mode=keyword。"""
    store = KnowledgeStore(db, root=str(tmp_path))
    store.upsert("研报A", "本文分析新能源汽车产业链上下游格局与竞争壁垒。" * 3)
    hits = store.search("新能源", top_k=5)
    assert hits
    assert hits[0]["mode"] == "keyword"
    assert "新能源" in hits[0]["content"]
    assert hits[0]["title"] == "研报A"
    assert hits[0]["score"] > 0


def test_keyword_search_title_boost(db: Session, tmp_path: Path):
    """标题命中加权：同正文命中时优先返回标题含查询词的文档。"""
    store = KnowledgeStore(db, root=str(tmp_path))
    body = "茅台与白酒行业深度研究报告，关注品牌与渠道。" * 5
    titled = store.upsert("茅台", body)
    store.upsert("行业观察", body)
    hits = store.search("茅台", top_k=5)
    assert hits
    assert hits[0]["doc_id"] == titled["doc_id"]
    assert hits[0]["mode"] == "keyword"


def test_keyword_search_empty_query(db: Session, tmp_path: Path):
    store = KnowledgeStore(db, root=str(tmp_path))
    store.upsert("x", "hello world content")
    assert store.search("") == []
    assert store.search("   ") == []
