"""复盘。"""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_review import ReviewService

router = APIRouter(prefix="/review")


class ReviewIn(BaseModel):
    asof: date
    content: str
    deviations: list[dict] = []


@router.get("")
def list_reviews(db: Session = Depends(get_db)):
    return ReviewService(db).list_recent()


@router.get("/{asof}")
def get_review(asof: date, db: Session = Depends(get_db)):
    return ReviewService(db).get(asof)


@router.post("")
def upsert(body: ReviewIn, db: Session = Depends(get_db)):
    return ReviewService(db).upsert(body.asof, body.content, body.deviations)
