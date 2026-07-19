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


@router.get("/analytics/execution-quality")
def execution_quality(db: Session = Depends(get_db)):
    """纸成交执行质量（相对当日收盘滑点代理）。"""
    from desk_broker.execution_quality import analyze_paper_execution

    return analyze_paper_execution(db)


@router.get("/analytics/attribution")
def attribution(strategy_id: str | None = None, db: Session = Depends(get_db)):
    """轻量策略 vs 买入持有对比。"""
    from desk_review.attribution import simple_vs_buyhold

    return simple_vs_buyhold(db, strategy_id=strategy_id)


@router.get("/{asof}")
def get_review(asof: date, db: Session = Depends(get_db)):
    return ReviewService(db).get(asof)


@router.post("")
def upsert(body: ReviewIn, db: Session = Depends(get_db)):
    return ReviewService(db).upsert(body.asof, body.content, body.deviations)
