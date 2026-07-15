"""交易日历与停牌。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import SuspensionEvent, TradeCalendar

logger = logging.getLogger(__name__)


class TradeCalendarClient(Protocol):
    """交易日历数据源。"""

    def trade_days(self, start: date, end: date) -> list[tuple[date, bool]]:
        """返回 (日期, 是否开市) 列表。"""
        ...


class CalendarSync:
    """将外部日历 upsert 到 trade_calendar。"""

    def __init__(self, db: Session, client: TradeCalendarClient) -> None:
        self.db = db
        self.client = client

    def run(self, start: date, end: date) -> int:
        """
        同步 [start, end] 日历。

        @returns: 写入/更新天数
        """
        n = 0
        for cal_date, is_open in self.client.trade_days(start, end):
            row = self.db.scalar(select(TradeCalendar).where(TradeCalendar.cal_date == cal_date))
            if row:
                row.is_open = is_open
                row.note = "" if is_open else (row.note or "休市")
            else:
                self.db.add(
                    TradeCalendar(
                        cal_date=cal_date,
                        is_open=is_open,
                        note="" if is_open else "休市",
                    )
                )
            n += 1
        self.db.flush()
        return n


class CalendarService:
    """交易日历 / 停牌服务。"""

    def __init__(self, db: Session):
        self.db = db

    def ensure_year(self, year: int) -> int:
        """确保某年日历存在（周末休市，简单规则）。"""
        existing = self.db.scalar(
            select(TradeCalendar).where(TradeCalendar.cal_date >= date(year, 1, 1)).limit(1)
        )
        if existing:
            return 0
        d = date(year, 1, 1)
        end = date(year, 12, 31)
        n = 0
        while d <= end:
            self.db.add(
                TradeCalendar(cal_date=d, is_open=d.weekday() < 5, note="" if d.weekday() < 5 else "周末")
            )
            n += 1
            d += timedelta(days=1)
        self.db.flush()
        return n

    def is_trade_day(self, day: date) -> bool:
        """是否交易日；库中无该日记录时警告并周末 fallback。"""
        row = self.db.scalar(select(TradeCalendar).where(TradeCalendar.cal_date == day))
        if row is None:
            logger.warning("日历未同步，使用周末 fallback: %s", day)
            return day.weekday() < 5
        return bool(row.is_open)

    def require_trade_day(self, day: date) -> bool:
        """供 jobs 门闸：仅当确认为交易日时返回 True。"""
        return self.is_trade_day(day)

    def next_trade_day(self, day: date | None = None) -> date:
        """下一交易日。"""
        cur = (day or date.today()) + timedelta(days=1)
        for _ in range(30):
            if self.is_trade_day(cur):
                return cur
            cur += timedelta(days=1)
        return cur

    def month_view(self, year: int, month: int) -> list[dict[str, Any]]:
        """月历视图。"""
        self.ensure_year(year)
        rows = self.db.scalars(
            select(TradeCalendar).where(
                TradeCalendar.cal_date >= date(year, month, 1),
                TradeCalendar.cal_date < (
                    date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
                ),
            )
        ).all()
        return [{"date": r.cal_date.isoformat(), "is_open": r.is_open, "note": r.note} for r in rows]

    def list_suspensions(self) -> list[dict[str, Any]]:
        """停牌/复牌事件。"""
        rows = self.db.scalars(
            select(SuspensionEvent).order_by(SuspensionEvent.effective_date.desc())
        ).all()
        return [
            {
                "symbol": r.symbol,
                "name": r.name,
                "event_type": r.event_type,
                "effective_date": r.effective_date.isoformat(),
                "reason": r.reason,
                "scope": r.scope,
            }
            for r in rows
        ]
