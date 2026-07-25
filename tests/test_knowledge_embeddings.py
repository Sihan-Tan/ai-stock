"""知识库 embedding 存取与 vector/hybrid 检索。"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

from desk_knowledge import KnowledgeStore
from desk_knowledge.embeddings import (
    cosine_similarity,
    embed_texts,
    load_doc_embeddings,
    resolve_embedding_config,
    save_doc_embeddings,
)


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch):
    """内存库 Session；清空 embedding/llm key，避免 create 误调真实 API。"""
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "")
    monkeypatch.setenv("EMBEDDING_MODEL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("KNOWLEDGE_RETRIEVAL", "keyword")
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


def test_resolve_embedding_config_none_without_key():
    s = SimpleNamespace(
        embedding_api_key="",
        llm_api_key="",
        embedding_base_url="",
        llm_base_url="https://api.example.com/v1",
        embedding_model="",
    )
    assert resolve_embedding_config(s) is None


def test_resolve_embedding_config_falls_back_llm():
    s = SimpleNamespace(
        embedding_api_key="",
        llm_api_key="sk-llm",
        embedding_base_url="",
        llm_base_url="https://api.example.com/v1",
        embedding_model="",
    )
    assert resolve_embedding_config(s) == (
        "sk-llm",
        "https://api.example.com/v1",
        "text-embedding-3-small",
    )


def test_resolve_embedding_config_skips_deepseek_llm_fallback():
    """DeepSeek Chat API 无 /embeddings，仅 LLM 配置时不应尝试向量化。"""
    s = SimpleNamespace(
        embedding_api_key="",
        llm_api_key="sk-deepseek",
        embedding_base_url="",
        llm_base_url="https://api.deepseek.com/v1",
        embedding_model="",
    )
    assert resolve_embedding_config(s) is None


def test_resolve_embedding_config_explicit_embedding_over_deepseek_llm():
    """显式 Embedding 端点时可用，即使 LLM 是 DeepSeek。"""
    s = SimpleNamespace(
        embedding_api_key="sk-openai",
        llm_api_key="sk-deepseek",
        embedding_base_url="https://api.openai.com/v1",
        llm_base_url="https://api.deepseek.com/v1",
        embedding_model="text-embedding-3-small",
    )
    assert resolve_embedding_config(s) == (
        "sk-openai",
        "https://api.openai.com/v1",
        "text-embedding-3-small",
    )


def test_resolve_embedding_config_emb_key_ignores_deepseek_base():
    """仅有 Embedding Key、无 Embedding Base 时，不回退 DeepSeek base。"""
    s = SimpleNamespace(
        embedding_api_key="sk-openai",
        llm_api_key="sk-deepseek",
        embedding_base_url="",
        llm_base_url="https://api.deepseek.com/v1",
        embedding_model="",
    )
    assert resolve_embedding_config(s) == (
        "sk-openai",
        "",
        "text-embedding-3-small",
    )


def test_save_load_roundtrip(tmp_path: Path):
    arr = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
    save_doc_embeddings(tmp_path, "docabc", arr)
    loaded = load_doc_embeddings(tmp_path, "docabc")
    assert loaded is not None
    np.testing.assert_array_almost_equal(loaded, arr)
    assert load_doc_embeddings(tmp_path, "missing") is None


def test_cosine_similarity_prefers_aligned():
    mat = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
    scores = cosine_similarity(mat, np.array([1.0, 0.0]))
    assert scores[0] > scores[1]


def test_embed_texts_empty():
    out = embed_texts([], api_key="k", base_url="", model="m")
    assert out.shape == (0, 0)


def test_embed_texts_calls_openai(monkeypatch: pytest.MonkeyPatch):
    """Mock OpenAI embeddings.create 返回固定向量。"""

    class _Item:
        def __init__(self, index: int, embedding: list[float]):
            self.index = index
            self.embedding = embedding

    class _Resp:
        def __init__(self, data: list[_Item]):
            self.data = data

    class _Embeddings:
        def create(self, *, model: str, input: list[str]):  # noqa: A002
            assert model == "text-embedding-3-small"
            return _Resp([_Item(i, [float(i + 1), 0.0]) for i in range(len(input))])

    class _Client:
        def __init__(self, **kwargs: Any):
            self.embeddings = _Embeddings()

    monkeypatch.setattr("openai.OpenAI", _Client)
    arr = embed_texts(["a", "b"], api_key="k", base_url="http://x", model="text-embedding-3-small")
    assert arr.shape == (2, 2)
    np.testing.assert_array_almost_equal(arr[0], [1.0, 0.0])
    np.testing.assert_array_almost_equal(arr[1], [2.0, 0.0])


def test_vector_search_ranks_closer_chunk(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """语义更近的切片应排在前面。"""
    store = KnowledgeStore(db, root=str(tmp_path))
    a = store.create("A", "苹果 水果 甜味 红富士 " * 20)
    b = store.create("B", "汽车 发动机 轮胎 底盘 " * 20)

    # 手工写入向量：query≈A，远离 B
    save_doc_embeddings(tmp_path, a["doc_id"], np.array([[1.0, 0.0]], dtype=np.float64))
    save_doc_embeddings(tmp_path, b["doc_id"], np.array([[0.0, 1.0]], dtype=np.float64))

    class _Item:
        def __init__(self, index: int, embedding: list[float]):
            self.index = index
            self.embedding = embedding

    class _Resp:
        def __init__(self, data: list[_Item]):
            self.data = data

    class _Embeddings:
        def create(self, *, model: str, input: list[str]):  # noqa: A002
            # 查询向量靠近「苹果」文档
            return _Resp([_Item(i, [1.0, 0.0]) for i in range(len(input))])

    class _Client:
        def __init__(self, **kwargs: Any):
            self.embeddings = _Embeddings()

    monkeypatch.setattr("openai.OpenAI", _Client)
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    get_settings.cache_clear()

    hits = store.search("任意查询", top_k=5, mode="vector")
    assert hits
    assert hits[0]["doc_id"] == a["doc_id"]
    assert hits[0]["mode"] == "vector"
    assert hits[0]["score"] >= (hits[1]["score"] if len(hits) > 1 else 0)


def test_hybrid_without_key_falls_back_keyword(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    store = KnowledgeStore(db, root=str(tmp_path))
    store.create("情绪", "高位晋级率连续两日低于百分之三十则退潮")
    hits = store.search("晋级率", top_k=3, mode="hybrid")
    assert hits
    assert hits[0]["mode"] == "keyword"
    assert hits[0].get("mode_requested") == "hybrid"


def test_vector_without_key_raises(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    store = KnowledgeStore(db, root=str(tmp_path))
    store.create("x", "hello world content enough")
    with pytest.raises(ValueError, match="未配置 embedding"):
        store.search("hello", mode="vector")
