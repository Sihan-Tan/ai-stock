"""龙虎榜。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import LhbDaily, LhbSeat
from desk_lhb.akshare_client import AkshareLhbClient, FakeLhbClient, is_institution_seat
from desk_lhb.ingest import LhbDailyIngestor

__all__ = [
    "LhbService",
    "LhbDailyIngestor",
    "AkshareLhbClient",
    "FakeLhbClient",
    "is_institution_seat",
]


class LhbService:
    """龙虎榜服务。"""

    def __init__(self, db: Session):
        self.db = db

    def by_date(self, day: date | None = None) -> list[dict[str, Any]]:
        """按日查询上榜与席位。"""
        day = day or date.today()
        rows = self.db.scalars(select(LhbDaily).where(LhbDaily.asof == day)).all()
        out = []
        for r in rows:
            seats = self.db.scalars(select(LhbSeat).where(LhbSeat.lhb_id == r.id)).all()
            out.append(
                {
                    "symbol": r.symbol,
                    "name": r.name,
                    "reason": r.reason,
                    "net_buy": r.net_buy,
                    "seats": [
                        {
                            "side": s.side,
                            "seat_name": s.seat_name,
                            "amount": s.amount,
                            "is_institution": s.is_institution,
                        }
                        for s in seats
                    ],
                }
            )
        return out

    def seed_demo(self, day: date | None = None) -> None:
        """演示数据。"""
        day = day or date.today()
        if self.db.scalar(select(LhbDaily).where(LhbDaily.asof == day)):
            return
        row = LhbDaily(
            asof=day,
            symbol="300750.SZ",
            name="宁德时代",
            reason="日振幅异常",
            net_buy=1.2e8,
        )
        self.db.add(row)
        self.db.flush()
        self.db.add_all(
            [
                LhbSeat(
                    lhb_id=row.id,
                    side="buy",
                    seat_name="某证券上海XX路",
                    amount=8.2e7,
                    is_institution=False,
                ),
                LhbSeat(
                    lhb_id=row.id,
                    side="sell",
                    seat_name="机构专用",
                    amount=5.5e7,
                    is_institution=True,
                ),
            ]
        )
        self.db.flush()
