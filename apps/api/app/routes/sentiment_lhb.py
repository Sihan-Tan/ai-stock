"""打板情绪 / 龙虎榜。"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_lhb import LhbService
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import MockQmtMarketData
from desk_sentiment import SentimentService

router = APIRouter()


def _jobs(db: Session) -> MarketJobs:
    return MarketJobs(db, md=MockQmtMarketData(instruments=[]))


@router.post("/sentiment/seed")
def seed_sentiment(db: Session = Depends(get_db)):
    SentimentService(db).seed_demo()
    return {"ok": True}


@router.get("/sentiment/snapshot")
def sentiment_snapshot(asof: date | None = None, db: Session = Depends(get_db)):
    return SentimentService(db).snapshot(asof)


@router.post("/sentiment/jobs/sync")
def sentiment_sync(asof: date | None = None, db: Session = Depends(get_db)):
    return _jobs(db).sync_sentiment_daily(asof=asof)


@router.post("/lhb/seed")
def seed_lhb(db: Session = Depends(get_db)):
    LhbService(db).seed_demo()
    return {"ok": True}


@router.get("/lhb")
def lhb(asof: date | None = None, db: Session = Depends(get_db)):
    return LhbService(db).by_date(asof)


@router.post("/lhb/jobs/sync")
def lhb_sync(asof: date | None = None, db: Session = Depends(get_db)):
    return _jobs(db).sync_lhb_daily(asof=asof)
