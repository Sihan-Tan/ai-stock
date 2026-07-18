"""晨会。"""

from datetime import date
import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_db.models import MorningBriefRow, MorningStrongPick
from desk_market.auction_ingest import AuctionSnapshotIngestor
from desk_morning_brief import MorningBriefService

router = APIRouter(prefix="/morning")


def _get_market_data():
    """与行情路由一致：优先 xtdata。"""
    from app.routes.market import get_market_data

    return get_market_data()


@router.post("/preopen")
def preopen(asof: date | None = None, db: Session = Depends(get_db)):
    return MorningBriefService(db).run_preopen(asof).model_dump()


@router.post("/post-auction")
def post_auction(asof: date | None = None, db: Session = Depends(get_db)):
    """
    竞价选拔：若当日尚无快照则先从行情源拉取自选竞价快照。
    """
    asof = asof or date.today()
    try:
        AuctionSnapshotIngestor(db, _get_market_data(), asof=asof).run()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return MorningBriefService(db).run_post_auction(asof).model_dump()


@router.get("/latest")
def morning_latest(asof: date | None = None, db: Session = Depends(get_db)):
    """
    读取当日晨会文案与强势选拔结果。

    @param asof: 交易日，默认今天
    """
    asof = asof or date.today()
    briefs = db.scalars(
        select(MorningBriefRow)
        .where(MorningBriefRow.asof == asof)
        .order_by(MorningBriefRow.id.desc())
    ).all()
    by_stage: dict[str, dict] = {}
    for row in briefs:
        if row.stage in by_stage:
            continue
        try:
            extras = json.loads(row.extras_json or "{}")
        except json.JSONDecodeError:
            extras = {}
        by_stage[row.stage] = {
            "asof": row.asof.isoformat(),
            "stage": row.stage,
            "content": row.content,
            "extras": extras,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    picks = db.scalars(
        select(MorningStrongPick)
        .where(MorningStrongPick.asof == asof)
        .order_by(MorningStrongPick.score.desc())
    ).all()
    boards = []
    stocks = []
    for pick in picks:
        try:
            meta = json.loads(pick.meta_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        item = {
            "code": pick.code,
            "name": pick.name,
            "score": pick.score,
            **meta,
        }
        if pick.pick_type == "board":
            boards.append(item)
        else:
            stocks.append(item)
    return {"asof": asof.isoformat(), "briefs": by_stage, "boards": boards, "stocks": stocks}
