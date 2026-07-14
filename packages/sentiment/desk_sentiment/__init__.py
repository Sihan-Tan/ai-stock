"""打板情绪。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import LimitUpStat, LimitUpStock


class SentimentService:
    """涨停情绪服务。"""

    def __init__(self, db: Session):
        self.db = db

    def snapshot(self, asof: date | None = None) -> dict[str, Any]:
        """情绪快照。"""
        asof = asof or date.today()
        stat = self.db.scalar(select(LimitUpStat).where(LimitUpStat.asof == asof))
        stocks = self.db.scalars(
            select(LimitUpStock).where(LimitUpStock.asof == asof).order_by(LimitUpStock.board_height.desc())
        ).all()
        return {
            "asof": asof.isoformat(),
            "limit_up_count": stat.limit_up_count if stat else 0,
            "limit_down_count": stat.limit_down_count if stat else 0,
            "max_board": stat.max_board if stat else 0,
            "promote_rate": stat.promote_rate if stat else 0.0,
            "break_rate": stat.break_rate if stat else 0.0,
            "ladder": [
                {
                    "symbol": s.symbol,
                    "name": s.name,
                    "board_height": s.board_height,
                    "seal_amount": s.seal_amount,
                    "concept": s.concept,
                    "status": s.status,
                }
                for s in stocks
            ],
        }

    def seed_demo(self, asof: date | None = None) -> None:
        """演示数据。"""
        asof = asof or date.today()
        if self.db.scalar(select(LimitUpStat).where(LimitUpStat.asof == asof)):
            return
        self.db.add(
            LimitUpStat(
                asof=asof,
                limit_up_count=68,
                limit_down_count=12,
                max_board=7,
                promote_rate=0.42,
                break_rate=0.18,
            )
        )
        self.db.add_all(
            [
                LimitUpStock(
                    asof=asof,
                    symbol="000001.SZ",
                    name="示例连板",
                    board_height=7,
                    seal_amount=2.1e8,
                    concept="AI应用",
                    status="sealed",
                ),
                LimitUpStock(
                    asof=asof,
                    symbol="600001.SH",
                    name="示例破板",
                    board_height=1,
                    seal_amount=0,
                    concept="机器人",
                    status="broken",
                ),
            ]
        )
        self.db.flush()
