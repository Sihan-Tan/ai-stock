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
