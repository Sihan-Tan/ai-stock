"""晨会。"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_morning_brief import MorningBriefService

router = APIRouter(prefix="/morning")


@router.post("/preopen")
def preopen(asof: date | None = None, db: Session = Depends(get_db)):
    return MorningBriefService(db).run_preopen(asof).model_dump()


@router.post("/post-auction")
def post_auction(asof: date | None = None, db: Session = Depends(get_db)):
    return MorningBriefService(db).run_post_auction(asof).model_dump()
