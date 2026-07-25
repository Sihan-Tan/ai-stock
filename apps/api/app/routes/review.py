"""复盘。"""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_db import get_db
from desk_review import ReviewService, generate_review
from desk_review.scheduler import get_review_scheduler_status

router = APIRouter(prefix="/review")


class ReviewIn(BaseModel):
    asof: date
    content: str
    deviations: list[dict] = []


class GenerateIn(BaseModel):
    asof: date | None = None
    strategy_id: str | None = None
    force: bool = True


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


@router.get("/auto-status")
def auto_status():
    """自动复盘开关与最近调度。"""
    st = get_review_scheduler_status()
    st["review_auto"] = bool(get_settings().review_auto)
    return st


@router.post("/generate")
def generate(body: GenerateIn | None = None, db: Session = Depends(get_db)):
    """手动/强制 LLM 生成复盘。"""
    payload = body or GenerateIn()
    asof = payload.asof or date.today()
    out = generate_review(
        db,
        asof,
        strategy_id=payload.strategy_id,
        force=bool(payload.force),
    )
    if out.get("status") == "ok":
        db.commit()
    return out


@router.get("/{asof}")
def get_review(asof: date, db: Session = Depends(get_db)):
    row = ReviewService(db).get(asof)
    if row is None:
        return {"asof": asof.isoformat(), "content": "", "deviations": []}
    return row


@router.post("")
def upsert(body: ReviewIn, db: Session = Depends(get_db)):
    return ReviewService(db).upsert(body.asof, body.content, body.deviations)
