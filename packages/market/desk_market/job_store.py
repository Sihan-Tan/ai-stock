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

    def get(self, run_id: int) -> MarketJobRun | None:
        """按主键取运行记录。"""
        return self.db.get(MarketJobRun, run_id)

    def has_running(self, job_id: str) -> bool:
        """同 job_id 是否已有 running。"""
        row = self.db.scalar(
            select(MarketJobRun)
            .where(MarketJobRun.job_id == job_id, MarketJobRun.status == "running")
            .limit(1)
        )
        return row is not None

    def progress(self, row: MarketJobRun, *, symbols_done: int, message: str = "") -> None:
        """
        更新进行中进度并提交，供其他会话轮询可见。

        @param row: 运行中行
        @param symbols_done: 已完成标的数
        @param message: 可选短消息
        """
        row.symbols_done = symbols_done
        if message:
            row.message = message
        self.db.commit()

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

    @staticmethod
    def to_dict(r: MarketJobRun) -> dict[str, Any]:
        """序列化单条运行记录。"""
        return {
            "id": r.id,
            "job_id": r.job_id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "symbols_done": r.symbols_done,
            "error_summary": r.error_summary,
            "message": r.message,
        }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近任务状态。"""
        rows = self.db.scalars(
            select(MarketJobRun).order_by(MarketJobRun.id.desc()).limit(limit)
        ).all()
        return [self.to_dict(r) for r in rows]
