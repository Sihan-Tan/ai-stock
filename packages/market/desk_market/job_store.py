"""MarketJobRun 写入与查询。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import MarketJobRun


class JobStore:
    """任务运行记录仓储。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def start(self, job_id: str) -> MarketJobRun:
        """开始一次任务运行。"""
        row = MarketJobRun(
            job_id=job_id,
            status="running",
            started_at=datetime.utcnow(),
            symbols_done=0,
            error_summary="",
            message="",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def finish(
        self,
        row: MarketJobRun,
        *,
        status: str,
        symbols_done: int = 0,
        error_summary: str = "",
        message: str = "",
    ) -> MarketJobRun:
        """结束任务并写入结果。"""
        row.status = status
        row.finished_at = datetime.utcnow()
        row.symbols_done = symbols_done
        row.error_summary = error_summary
        row.message = message
        self.db.flush()
        return row

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近任务状态。"""
        rows = self.db.scalars(
            select(MarketJobRun).order_by(MarketJobRun.id.desc()).limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "job_id": r.job_id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "symbols_done": r.symbols_done,
                "error_summary": r.error_summary,
                "message": r.message,
            }
            for r in rows
        ]
