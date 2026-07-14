"""研报 / 笔记知识库。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import KnowledgeChunk, KnowledgeDoc


class KnowledgeStore:
    """本地文件 + DB 切片。"""

    def __init__(self, db: Session, root: str = "data/knowledge"):
        self.db = db
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def upsert(self, title: str, content: str, doc_type: str = "markdown", tags: str = "") -> dict[str, Any]:
        """上传/写入文档并切片。"""
        doc_id = uuid.uuid4().hex[:12]
        path = self.root / f"{doc_id}.md"
        path.write_text(content, encoding="utf-8")
        self.db.add(
            KnowledgeDoc(
                doc_id=doc_id,
                title=title,
                doc_type=doc_type,
                tags=tags,
                path=str(path),
            )
        )
        chunks = self._chunk(content)
        for i, ch in enumerate(chunks):
            self.db.add(KnowledgeChunk(doc_id=doc_id, chunk_index=i, content=ch))
        self.db.flush()
        return {"doc_id": doc_id, "title": title, "chunks": len(chunks)}

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """关键词检索（简易）。"""
        q = query.lower()
        rows = self.db.scalars(select(KnowledgeChunk)).all()
        scored = []
        for r in rows:
            text = r.content.lower()
            score = sum(1 for token in re.split(r"\s+", q) if token and token in text)
            if score:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"doc_id": r.doc_id, "chunk_index": r.chunk_index, "content": r.content, "score": s}
            for s, r in scored[:top_k]
        ]

    def list_docs(self) -> list[dict[str, Any]]:
        """文档列表。"""
        rows = self.db.scalars(select(KnowledgeDoc).order_by(KnowledgeDoc.id.desc())).all()
        return [
            {
                "doc_id": r.doc_id,
                "title": r.title,
                "doc_type": r.doc_type,
                "tags": r.tags,
                "path": r.path,
            }
            for r in rows
        ]

    @staticmethod
    def _chunk(content: str, size: int = 400) -> list[str]:
        content = content.strip()
        if not content:
            return []
        return [content[i : i + size] for i in range(0, len(content), size)]
