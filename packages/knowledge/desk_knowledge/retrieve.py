"""知识库检索：关键词 / 向量 / 混合打分。"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import KnowledgeChunk, KnowledgeDoc

from desk_knowledge.embeddings import cosine_similarity, load_doc_embeddings

# 仅标点/符号的 token（过滤用）
_PUNCT_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)
# jieba 不可用时的回退分词
_FALLBACK_TOKEN = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]+")


def tokenize(query: str) -> list[str]:
    """对查询做中文友好分词。

    优先 ``jieba.lcut``，并合并空白切分结果；未安装 jieba 时回退正则。
    结果小写，去掉空串与纯标点 token。

    Args:
        query: 原始查询字符串。

    Returns:
        去重后的 token 列表（顺序不稳定）。
    """
    q = (query or "").strip()
    if not q:
        return []

    raw: set[str] = set()
    for part in re.split(r"\s+", q):
        if part:
            raw.add(part)

    try:
        import jieba

        for t in jieba.lcut(q):
            if t and not t.isspace():
                raw.add(t)
    except ImportError:
        for t in _FALLBACK_TOKEN.findall(q):
            raw.add(t)

    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        tok = t.strip().lower()
        if not tok or _PUNCT_ONLY.fullmatch(tok):
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def score_chunk(
    tokens: list[str],
    content: str,
    title: str = "",
    tags: str = "",
    *,
    title_boost: int = 2,
    tag_boost: int = 1,
) -> float:
    """按 token 命中内容计数，并对标题/标签命中加权。

    Args:
        tokens: 已小写的查询 token。
        content: 切片正文。
        title: 文档标题。
        tags: 文档标签字符串。
        title_boost: 标题命中额外加分。
        tag_boost: 标签命中额外加分。

    Returns:
        非负分数；无命中为 0。
    """
    if not tokens:
        return 0.0
    text = (content or "").lower()
    title_l = (title or "").lower()
    tags_l = (tags or "").lower()
    score = 0.0
    for tok in tokens:
        if tok in text:
            score += 1.0
        if tok in title_l:
            score += float(title_boost)
        if tok in tags_l:
            score += float(tag_boost)
    return score


def keyword_search(db: Session, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """关键词检索：分词 → 切片打分 → 返回 top_k。

    Args:
        db: SQLAlchemy Session。
        query: 查询字符串；空串返回 []。
        top_k: 返回条数上限。

    Returns:
        命中列表，每项含 doc_id/title/chunk_index/content/score/mode。
    """
    q = (query or "").strip()
    if not q:
        return []
    tokens = tokenize(q)
    if not tokens:
        return []

    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDoc).join(
            KnowledgeDoc, KnowledgeChunk.doc_id == KnowledgeDoc.doc_id
        )
    ).all()

    scored: list[tuple[float, KnowledgeChunk, KnowledgeDoc]] = []
    for chunk, doc in rows:
        s = score_chunk(tokens, chunk.content, doc.title or "", doc.tags or "")
        if s > 0:
            scored.append((s, chunk, doc))
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "doc_id": chunk.doc_id,
            "title": doc.title,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": score,
            "mode": "keyword",
        }
        for score, chunk, doc in scored[: max(0, top_k)]
    ]


def _normalize_score_map(scores: dict[tuple[str, int], float]) -> dict[tuple[str, int], float]:
    """将分数映射线性归一化到 [0, 1]。"""
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return {k: (1.0 if v > 0 else 0.0) for k, v in scores.items()}
    span = hi - lo
    return {k: (v - lo) / span for k, v in scores.items()}


def vector_search(
    db: Session,
    root: Path | str,
    query: str,
    top_k: int = 5,
    embed_fn: Callable[[list[str]], np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    """向量检索：query embedding × 各文档 npy 行余弦相似。

    Args:
        db: SQLAlchemy Session。
        root: 知识库根目录（含 embeddings/）。
        query: 查询字符串；空串返回 []。
        top_k: 返回条数上限。
        embed_fn: ``texts -> ndarray (n, dim)``；必填。

    Returns:
        命中列表，``mode=vector``。
    """
    q = (query or "").strip()
    if not q:
        return []
    if embed_fn is None:
        raise ValueError("vector_search 需要 embed_fn")

    q_mat = embed_fn([q])
    if q_mat.size == 0:
        return []
    q_vec = q_mat[0]

    root_path = Path(root)
    docs = db.scalars(select(KnowledgeDoc)).all()
    scored: list[tuple[float, str, int, str, str]] = []

    for doc in docs:
        arr = load_doc_embeddings(root_path, doc.doc_id)
        if arr is None or arr.size == 0:
            continue
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        sims = cosine_similarity(arr, q_vec)
        chunks = db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.doc_id == doc.doc_id)
            .order_by(KnowledgeChunk.chunk_index)
        ).all()
        by_index = {c.chunk_index: c for c in chunks}
        for row_i, sim in enumerate(sims):
            chunk = by_index.get(row_i)
            if chunk is None:
                continue
            scored.append(
                (float(sim), doc.doc_id, chunk.chunk_index, chunk.content, doc.title or "")
            )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "doc_id": doc_id,
            "title": title,
            "chunk_index": chunk_index,
            "content": content,
            "score": score,
            "mode": "vector",
        }
        for score, doc_id, chunk_index, content, title in scored[: max(0, top_k)]
    ]


def hybrid_search(
    db: Session,
    root: Path | str,
    query: str,
    top_k: int = 5,
    embed_fn: Callable[[list[str]], np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    """混合检索：归一化后 ``0.7 * vector + 0.3 * keyword``，按 (doc_id, chunk_index) 合并。

    Args:
        db: SQLAlchemy Session。
        root: 知识库根目录。
        query: 查询字符串。
        top_k: 返回条数上限。
        embed_fn: 向量化函数。

    Returns:
        命中列表，``mode=hybrid``。
    """
    q = (query or "").strip()
    if not q:
        return []

    # 取足够多的候选再融合截断
    pool = max(top_k * 20, 200)
    kw_hits = keyword_search(db, q, top_k=pool)
    vec_hits = vector_search(db, root, q, top_k=pool, embed_fn=embed_fn)

    kw_map: dict[tuple[str, int], float] = {
        (h["doc_id"], int(h["chunk_index"])): float(h["score"]) for h in kw_hits
    }
    vec_map: dict[tuple[str, int], float] = {
        (h["doc_id"], int(h["chunk_index"])): float(h["score"]) for h in vec_hits
    }
    meta: dict[tuple[str, int], dict[str, Any]] = {}
    for h in kw_hits + vec_hits:
        key = (h["doc_id"], int(h["chunk_index"]))
        if key not in meta:
            meta[key] = {"title": h.get("title", ""), "content": h.get("content", "")}

    kw_n = _normalize_score_map(kw_map)
    vec_n = _normalize_score_map(vec_map)
    keys = set(kw_n) | set(vec_n)
    combined: list[tuple[float, tuple[str, int]]] = []
    for key in keys:
        score = 0.7 * vec_n.get(key, 0.0) + 0.3 * kw_n.get(key, 0.0)
        if score > 0:
            combined.append((score, key))
    combined.sort(key=lambda x: x[0], reverse=True)

    out: list[dict[str, Any]] = []
    for score, (doc_id, chunk_index) in combined[: max(0, top_k)]:
        info = meta.get((doc_id, chunk_index), {})
        out.append(
            {
                "doc_id": doc_id,
                "title": info.get("title", ""),
                "chunk_index": chunk_index,
                "content": info.get("content", ""),
                "score": score,
                "mode": "hybrid",
            }
        )
    return out
