"""研报 / 笔记知识库。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from desk_db.models import KnowledgeChunk, KnowledgeDoc
from desk_knowledge.chunking import chunk_text
from desk_knowledge.pdf_extract import extract_pdf_text
from desk_knowledge.retrieve import hybrid_search, keyword_search, vector_search

_PREVIEW_MAX = 20000
_log = logging.getLogger(__name__)


def _ext_for_doc_type(doc_type: str) -> str:
    """按 doc_type 选择落盘扩展名。"""
    if doc_type == "text":
        return ".txt"
    if doc_type == "pdf":
        return ".pdf"
    return ".md"


class KnowledgeStore:
    """本地文件 + DB 切片。"""

    def __init__(self, db: Session, root: str = "data/knowledge"):
        self.db = db
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def upsert(self, title: str, content: str, doc_type: str = "markdown", tags: str = "") -> dict[str, Any]:
        """写入新文档并切片（总是新建，兼容 save_research_note）。"""
        return self.create(title, content, doc_type=doc_type, tags=tags)

    def create(self, title: str, content: str, doc_type: str = "markdown", tags: str = "") -> dict[str, Any]:
        """新建文档：落盘、写 DB、切片；有凭证时同步 embedding。"""
        text = content.strip()
        if not text:
            raise ValueError("正文不能为空")
        doc_id = uuid.uuid4().hex[:12]
        # 文本入库：markdown/note/research_note→.md，text→.txt；
        # pdf 原件应走 create_from_bytes，此处若误传 pdf 则仍写抽取文本为 .md
        file_type = "markdown" if doc_type == "pdf" else doc_type
        path = self.root / f"{doc_id}{_ext_for_doc_type(file_type)}"
        path.write_text(text, encoding="utf-8")
        self.db.add(
            KnowledgeDoc(
                doc_id=doc_id,
                title=title,
                doc_type=doc_type,
                tags=tags,
                path=str(path),
            )
        )
        chunks = chunk_text(text)
        for i, ch in enumerate(chunks):
            self.db.add(KnowledgeChunk(doc_id=doc_id, chunk_index=i, content=ch))
        self.db.flush()
        self._sync_embeddings(doc_id)
        return {"doc_id": doc_id, "title": title, "chunks": len(chunks), "chunk_count": len(chunks)}

    def create_from_bytes(
        self,
        title: str,
        raw: bytes,
        filename: str,
        tags: str = "",
    ) -> dict[str, Any]:
        """从上传字节创建文档（.pdf / .md / .txt）。

        PDF：原件落盘为 ``{doc_id}.pdf``，抽取文本后切片；``doc_type=pdf``，``path`` 指向 pdf。
        md/txt：解码 UTF-8 后落盘并切片。
        """
        suffix = Path(filename).suffix.lower()
        stem = Path(filename).stem
        resolved_title = (title or "").strip() or stem or "未命名"

        if suffix == ".pdf":
            if not raw:
                raise ValueError("文件不能为空")
            doc_id = uuid.uuid4().hex[:12]
            path = self.root / f"{doc_id}.pdf"
            path.write_bytes(raw)
            try:
                text = extract_pdf_text(path).strip()
            except ValueError:
                path.unlink(missing_ok=True)
                raise
            if not text:
                path.unlink(missing_ok=True)
                raise ValueError("无法抽取 PDF 文本，可能是扫描件，请先 OCR 后再上传")
            self.db.add(
                KnowledgeDoc(
                    doc_id=doc_id,
                    title=resolved_title,
                    doc_type="pdf",
                    tags=tags,
                    path=str(path),
                )
            )
            chunks = chunk_text(text)
            for i, ch in enumerate(chunks):
                self.db.add(KnowledgeChunk(doc_id=doc_id, chunk_index=i, content=ch))
            self.db.flush()
            self._sync_embeddings(doc_id)
            return {
                "doc_id": doc_id,
                "title": resolved_title,
                "chunks": len(chunks),
                "chunk_count": len(chunks),
            }

        if suffix in (".md", ".txt"):
            text = raw.decode("utf-8", errors="replace")
            doc_type = "markdown" if suffix == ".md" else "text"
            return self.create(resolved_title, text, doc_type=doc_type, tags=tags)

        raise ValueError("仅支持 .pdf / .md / .txt 文件")

    def update(
        self,
        doc_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: str | None = None,
        doc_type: str | None = None,
    ) -> dict[str, Any]:
        """更新元数据/正文；正文变更时重写文件、重建切片并尝试同步 embedding。"""
        row = self.db.scalar(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
        if row is None:
            raise KeyError(f"文档不存在: {doc_id}")
        if title is not None:
            row.title = title
        if tags is not None:
            row.tags = tags
        if doc_type is not None:
            row.doc_type = doc_type

        chunk_n = self._chunk_count(doc_id)
        content_changed = False
        if content is not None:
            text = content.strip()
            if not text:
                raise ValueError("正文不能为空")
            path = Path(row.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            # PDF 原件保留二进制；编辑正文时改为落盘 .md 并切换类型
            if path.suffix.lower() == ".pdf" or row.doc_type == "pdf":
                if path.exists() and path.suffix.lower() == ".pdf":
                    path.unlink()
                new_path = self.root / f"{doc_id}.md"
                new_path.write_text(text, encoding="utf-8")
                row.path = str(new_path)
                if doc_type is None:
                    row.doc_type = "markdown"
            else:
                path.write_text(text, encoding="utf-8")
            self.db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
            chunks = chunk_text(text)
            for i, ch in enumerate(chunks):
                self.db.add(KnowledgeChunk(doc_id=doc_id, chunk_index=i, content=ch))
            chunk_n = len(chunks)
            content_changed = True

        self.db.flush()
        if content_changed:
            self._sync_embeddings(doc_id)
        return {
            "doc_id": doc_id,
            "title": row.title,
            "tags": row.tags,
            "doc_type": row.doc_type,
            "chunks": chunk_n,
            "chunk_count": chunk_n,
        }

    def delete(self, doc_id: str) -> None:
        """删除切片、文档行与落盘文件（及可选向量文件）。"""
        row = self.db.scalar(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
        if row is None:
            raise KeyError(f"文档不存在: {doc_id}")
        self.db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
        path = Path(row.path)
        self.db.delete(row)
        self.db.flush()
        if path.exists():
            path.unlink()
        npy = self.root / "embeddings" / f"{doc_id}.npy"
        if npy.exists():
            npy.unlink()

    def get(self, doc_id: str, *, full: bool = False) -> dict[str, Any]:
        """文档详情：元数据、预览、切片数；full 时附全文。"""
        row = self.db.scalar(select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id))
        if row is None:
            raise KeyError(f"文档不存在: {doc_id}")
        path = Path(row.path)
        text = self._read_doc_text(row.doc_type, path)
        truncated = len(text) > _PREVIEW_MAX
        preview = text[:_PREVIEW_MAX]
        out: dict[str, Any] = {
            "doc_id": row.doc_id,
            "title": row.title,
            "doc_type": row.doc_type,
            "tags": row.tags,
            "path": row.path,
            "content_preview": preview,
            "content_truncated": truncated,
            "chunk_count": self._chunk_count(doc_id),
        }
        if full:
            out["content"] = text
        return out

    def search(self, query: str, top_k: int = 5, mode: str | None = None) -> list[dict[str, Any]]:
        """按模式检索；``mode`` 缺省取 ``settings.knowledge_retrieval``。

        - keyword：关键词
        - vector：无凭证 → ``ValueError("未配置 embedding")``
        - hybrid：无凭证 → 降级 keyword，并带 ``mode_requested=hybrid``
        """
        from desk_common.settings import get_settings
        from desk_knowledge.embeddings import embed_texts, resolve_embedding_config

        effective = (mode or get_settings().knowledge_retrieval or "keyword").strip().lower()
        if effective == "keyword":
            return keyword_search(self.db, query, top_k=top_k)

        cfg = resolve_embedding_config(get_settings())
        if effective == "vector":
            if cfg is None:
                raise ValueError("未配置 embedding")
            api_key, base_url, model = cfg

            def embed_fn(texts: list[str]):
                return embed_texts(texts, api_key=api_key, base_url=base_url, model=model)

            return vector_search(self.db, self.root, query, top_k=top_k, embed_fn=embed_fn)

        if effective == "hybrid":
            if cfg is None:
                hits = keyword_search(self.db, query, top_k=top_k)
                for h in hits:
                    h["mode"] = "keyword"
                    h["mode_requested"] = "hybrid"
                return hits
            api_key, base_url, model = cfg

            def embed_fn(texts: list[str]):
                return embed_texts(texts, api_key=api_key, base_url=base_url, model=model)

            return hybrid_search(self.db, self.root, query, top_k=top_k, embed_fn=embed_fn)

        return keyword_search(self.db, query, top_k=top_k)

    def list_docs(self) -> list[dict[str, Any]]:
        """文档列表（含 chunk_count）。"""
        rows = self.db.scalars(select(KnowledgeDoc).order_by(KnowledgeDoc.id.desc())).all()
        counts = dict(
            self.db.execute(
                select(KnowledgeChunk.doc_id, func.count()).group_by(KnowledgeChunk.doc_id)
            ).all()
        )
        return [
            {
                "doc_id": r.doc_id,
                "title": r.title,
                "doc_type": r.doc_type,
                "tags": r.tags,
                "path": r.path,
                "chunk_count": int(counts.get(r.doc_id, 0)),
            }
            for r in rows
        ]

    def _read_doc_text(self, doc_type: str, path: Path) -> str:
        """读取可展示正文；PDF 重新抽取文字层。"""
        if not path.exists():
            return ""
        if doc_type == "pdf" or path.suffix.lower() == ".pdf":
            try:
                return extract_pdf_text(path)
            except ValueError:
                return ""
        return path.read_text(encoding="utf-8")

    def _chunk_count(self, doc_id: str) -> int:
        """统计某文档切片数。"""
        n = self.db.scalar(
            select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id)
        )
        return int(n or 0)

    def _sync_embeddings(self, doc_id: str) -> None:
        """若已配置 embedding，则同步写入文档 npy；失败不阻断入库。"""
        from desk_common.settings import get_settings
        from desk_knowledge.embeddings import (
            embed_texts,
            resolve_embedding_config,
            save_doc_embeddings,
        )

        cfg = resolve_embedding_config(get_settings())
        if cfg is None:
            return
        try:
            api_key, base_url, model = cfg
            chunks = self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.doc_id == doc_id)
                .order_by(KnowledgeChunk.chunk_index)
            ).all()
            texts = [c.content for c in chunks]
            if not texts:
                return
            arr = embed_texts(texts, api_key=api_key, base_url=base_url, model=model)
            save_doc_embeddings(self.root, doc_id, arr)
        except Exception:  # noqa: BLE001
            _log.exception(
                "知识库 embedding 同步失败 doc_id=%s model=%s base_url=%s"
                "（DeepSeek 等 Chat API 无 embeddings；请在设置中单独配置 Embedding Base URL/Key）",
                doc_id,
                model,
                base_url or "(default)",
            )
