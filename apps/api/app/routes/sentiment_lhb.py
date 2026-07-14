"""打板情绪 / 龙虎榜。"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_lhb import LhbService
from desk_sentiment import SentimentService

router = APIRouter()


@router.post("/sentiment/seed")
def seed_sentiment(db: Session = Depends(get_db)):
    SentimentService(db).seed_demo()
    return {"ok": True}


@router.get("/sentiment/snapshot")
def sentiment_snapshot(asof: date | None = None, db: Session = Depends(get_db)):
    return SentimentService(db).snapshot(asof)


@router.post("/lhb/seed")
def seed_lhb(db: Session = Depends(get_db)):
    LhbService(db).seed_demo()
    return {"ok": True}


@router.get("/lhb")
def lhb(asof: date | None = None, db: Session = Depends(get_db)):
    return LhbService(db).by_date(asof)
