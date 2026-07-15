"""交易日历 / 停牌。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from desk_calendar import CalendarService
from desk_db import get_db

router = APIRouter(prefix="/calendar")


@router.get("/month")
def month(year: int, month: int, db: Session = Depends(get_db)):
    return CalendarService(db).month_view(year, month)


@router.get("/next-trade-day")
def next_day(db: Session = Depends(get_db)):
    d = CalendarService(db).next_trade_day()
    return {"next_trade_day": d.isoformat()}


@router.get("/suspensions")
def suspensions(db: Session = Depends(get_db)):
    return CalendarService(db).list_suspensions()
