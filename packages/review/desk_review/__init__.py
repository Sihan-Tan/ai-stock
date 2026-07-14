"""复盘笔记。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import ReviewNote


class ReviewService:
    """日复盘。"""

    def __init__(self, db: Session):
        self.db = db

    def upsert(self, asof: date, content: str, deviations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """新建或更新当日复盘。"""
        row = self.db.scalar(select(ReviewNote).where(ReviewNote.asof == asof))
        payload = json.dumps(deviations or [], ensure_ascii=False)
        if row:
            row.content = content
            row.deviations_json = payload
        else:
            row = ReviewNote(asof=asof, content=content, deviations_json=payload)
            self.db.add(row)
        self.db.flush()
        return {
            "asof": asof.isoformat(),
            "content": content,
            "deviations": deviations or [],
        }

    def get(self, asof: date) -> dict[str, Any] | None:
        """读取复盘。"""
        row = self.db.scalar(select(ReviewNote).where(ReviewNote.asof == asof))
        if not row:
            return None
        return {
            "asof": row.asof.isoformat(),
            "content": row.content,
            "deviations": json.loads(row.deviations_json or "[]"),
        }

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近复盘。"""
        rows = self.db.scalars(select(ReviewNote).order_by(ReviewNote.asof.desc()).limit(limit)).all()
        return [
            {
                "asof": r.asof.isoformat(),
                "content": r.content[:120],
            }
            for r in rows
        ]
