"""云端 Embedding 客户端与文档向量 npy 存取。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np

# 仅提供 Chat、无 OpenAI 兼容 /embeddings 的主机（回退 LLM base 时跳过）
_CHAT_ONLY_EMBEDDING_HOSTS = frozenset(
    {
        "api.deepseek.com",
    }
)


def _host_of(base_url: str) -> str:
    """从 base URL 取出小写 hostname。"""
    raw = (base_url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    return (urlparse(raw).hostname or "").lower()


def is_chat_only_embedding_base(base_url: str) -> bool:
    """判断 base 是否为已知不支持 embeddings 的 Chat 专用端点。"""
    return _host_of(base_url) in _CHAT_ONLY_EMBEDDING_HOSTS


def resolve_embedding_config(settings: Any) -> tuple[str, str, str] | None:
    """解析可用的 embedding 凭证。

    - key：``embedding_api_key``，否则 ``llm_api_key``
    - base：优先 ``embedding_base_url``；否则仅在 LLM base **支持 embeddings** 时回退
    - model：``embedding_model`` 或 ``text-embedding-3-small``

    DeepSeek 等 Chat 专用 API 无 ``/embeddings``，仅有 LLM 配置时返回 None
   （避免用 ``text-embedding-3-small`` 打 DeepSeek 得到 404）。

    Args:
        settings: 含 embedding_* / llm_* 字段的 Settings 对象。

    Returns:
        ``(api_key, base_url, model)``，或 None。
    """
    emb_key = (getattr(settings, "embedding_api_key", None) or "").strip()
    emb_base = (getattr(settings, "embedding_base_url", None) or "").strip()
    emb_model = (getattr(settings, "embedding_model", None) or "").strip()
    llm_key = (getattr(settings, "llm_api_key", None) or "").strip()
    llm_base = (getattr(settings, "llm_base_url", None) or "").strip()

    key = emb_key or llm_key
    if not key:
        return None

    if emb_base:
        base = emb_base
    elif emb_key:
        # 显式 Embedding Key：勿把 Chat-only 的 LLM base 绑过来（空=SDK 默认 OpenAI）
        base = "" if is_chat_only_embedding_base(llm_base) else llm_base
    else:
        # 全量回退 LLM：Chat-only 主机无法做向量
        if is_chat_only_embedding_base(llm_base):
            return None
        base = llm_base

    if is_chat_only_embedding_base(base):
        return None

    model = emb_model or "text-embedding-3-small"
    return key, base, model


def embed_texts(
    texts: list[str],
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> np.ndarray:
    """调用 OpenAI 兼容 embeddings API，返回 shape ``(n, dim)``。

    Args:
        texts: 待向量化文本列表。
        api_key: API Key。
        base_url: Base URL；空串时由 SDK 默认。
        model: 模型名。

    Returns:
        float64 数组；空列表返回 shape ``(0, 0)``。
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float64)

    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    resp = client.embeddings.create(model=model, input=texts)
    ordered = sorted(resp.data, key=lambda d: d.index)
    return np.asarray([d.embedding for d in ordered], dtype=np.float64)


def save_doc_embeddings(root: Path, doc_id: str, arr: np.ndarray) -> Path:
    """将文档向量矩阵保存为 ``root/embeddings/{doc_id}.npy``。

    Args:
        root: 知识库根目录。
        doc_id: 文档 ID。
        arr: shape ``(n_chunks, dim)``。

    Returns:
        写入路径。
    """
    path = Path(root) / "embeddings" / f"{doc_id}.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, arr)
    return path


def load_doc_embeddings(root: Path, doc_id: str) -> np.ndarray | None:
    """加载文档向量；文件不存在返回 None。

    Args:
        root: 知识库根目录。
        doc_id: 文档 ID。

    Returns:
        ndarray 或 None。
    """
    path = Path(root) / "embeddings" / f"{doc_id}.npy"
    if not path.is_file():
        return None
    return np.load(path)


def cosine_similarity(matrix: np.ndarray, query: np.ndarray) -> np.ndarray:
    """计算矩阵各行与查询向量的余弦相似度。

    Args:
        matrix: shape ``(n, dim)``。
        query: shape ``(dim,)`` 或 ``(1, dim)``。

    Returns:
        shape ``(n,)`` 的相似度分数；空矩阵返回空一维数组。
    """
    mat = np.asarray(matrix, dtype=np.float64)
    q = np.asarray(query, dtype=np.float64).reshape(-1)
    if mat.size == 0:
        return np.zeros((0,), dtype=np.float64)
    if mat.ndim == 1:
        mat = mat.reshape(1, -1)
    denom = np.linalg.norm(mat, axis=1) * (np.linalg.norm(q) + 1e-12)
    denom = np.where(denom == 0, 1e-12, denom)
    return (mat @ q) / denom
