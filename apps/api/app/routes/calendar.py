"""交易日历 / 财经事件 / 停牌。"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from desk_calendar import CalendarEventService, CalendarService
from desk_db import get_db

router = APIRouter(prefix="/calendar")


@router.get("/month")
def month(year: int, month: int, db: Session = Depends(get_db)):
    """月度开休市。"""
    return CalendarService(db).month_view(year, month)


@router.get("/next-trade-day")
def next_day(db: Session = Depends(get_db)):
    """下一交易日。"""
    d = CalendarService(db).next_trade_day()
    return {"next_trade_day": d.isoformat()}


@router.get("/suspensions")
def suspensions(db: Session = Depends(get_db)):
    """停牌/复牌列表。"""
    return CalendarService(db).list_suspensions()


@router.get("/events/today")
def events_today(
    min_importance: int = Query(4, ge=1, le=5),
    db: Session = Depends(get_db),
):
    """
    当日重大新闻/事件。

    若库中无数据会自动 ensure（AkShare 或 seed）。
    """
    svc = CalendarEventService(db)
    svc.ensure_horizon(months=3)
    return {
        "asof": date.today().isoformat(),
        "items": svc.list_today_major(min_importance=min_importance),
    }


@router.get("/events")
def events_range(
    start: str | None = None,
    end: str | None = None,
    category: str | None = None,
    min_importance: int | None = Query(None, ge=1, le=5),
    months: int = Query(3, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """未来财经日历与相关催化剂（默认今天起 3 个月）。"""
    svc = CalendarEventService(db)
    today = date.today()
    start_d = date.fromisoformat(start) if start else today
    end_d = date.fromisoformat(end) if end else today + timedelta(days=months * 31)
    svc.ensure_horizon(months=months)
    items = svc.list_events(
        start_d,
        end_d,
        category=category,
        min_importance=min_importance,
    )
    return {
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "items": items,
    }


@router.post("/events/sync")
def events_sync(
    months: int = Query(3, ge=1, le=12),
    prefer_seed: bool = Query(False),
    db: Session = Depends(get_db),
):
    """强制同步财经事件（AkShare 失败则 seed）。"""
    return CalendarEventService(db).sync(months=months, prefer_seed=prefer_seed)
