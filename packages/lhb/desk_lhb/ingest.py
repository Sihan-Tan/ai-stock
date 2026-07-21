"""龙虎榜日终落库。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import LhbDaily, LhbSeat
from desk_lhb.akshare_client import LhbClient, is_institution_seat


class LhbDailyIngestor:
    """按 asof 替换写入 lhb_daily / lhb_seats。"""

    def __init__(self, db: Session, client: LhbClient, asof: date | None = None) -> None:
        self.db = db
        self.client = client
        self.asof = asof or date.today()

    def run(self) -> dict[str, Any]:
        """拉取并按日替换。"""
        payload = self.client.fetch_by_date(self.asof)
        olds = self.db.scalars(select(LhbDaily).where(LhbDaily.asof == self.asof)).all()
        old_ids = [o.id for o in olds]
        if old_ids:
            seats = self.db.scalars(select(LhbSeat).where(LhbSeat.lhb_id.in_(old_ids))).all()
            for s in seats:
                self.db.delete(s)
            for o in olds:
                self.db.delete(o)
            self.db.flush()

        n_seats = 0
        for item in payload:
            raw_pct = item.get("pct_chg")
            pct_chg: float | None
            try:
                pct_chg = float(raw_pct) if raw_pct is not None else None
                if pct_chg is not None and pct_chg != pct_chg:
                    pct_chg = None
            except (TypeError, ValueError):
                pct_chg = None
            daily = LhbDaily(
                asof=self.asof,
                symbol=normalize_symbol(str(item.get("symbol") or "")),
                name=str(item.get("name") or ""),
                reason=str(item.get("reason") or ""),
                net_buy=float(item.get("net_buy") or 0.0),
                pct_chg=pct_chg,
            )
            self.db.add(daily)
            self.db.flush()
            for seat in item.get("seats") or []:
                name = str(seat.get("seat_name") or "")
                self.db.add(
                    LhbSeat(
                        lhb_id=daily.id,
                        side=str(seat.get("side") or "buy"),
                        seat_name=name,
                        amount=float(seat.get("amount") or 0.0),
                        is_institution=is_institution_seat(name),
                    )
                )
                n_seats += 1
        self.db.flush()
        return {"symbols_done": len(payload), "seats": n_seats, "errors": []}
