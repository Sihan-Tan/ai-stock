"""早盘选股（原晨会）。"""

from datetime import date
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_calendar import CalendarService
from desk_db import get_db
from desk_db.models import MorningBriefRow, MorningStrongPick
from desk_market.auction_ingest import AuctionSnapshotIngestor
from desk_ai.refine import ResearchRefineService, list_research_picks
from desk_morning_brief import MorningBriefService
from desk_morning_brief.bind import bind_morning_picks

router = APIRouter(prefix="/morning")


class MorningBindIn(BaseModel):
    """早盘标的写入自选。"""

    asof: date | None = None
    limit: int = Field(20, ge=1, le=100)
    symbols: list[str] | None = None


class ResearchRefineIn(BaseModel):
    """手动跑投研精选。"""

    asof: date | None = None
    top_n: int | None = Field(None, ge=1, le=20)
    min_confidence: float | None = Field(None, ge=0, le=100)


def _get_market_data():
    """与行情路由一致：优先 xtdata。"""
    from app.routes.market import get_market_data

    return get_market_data()


def _latest_payload(db: Session, asof: date) -> dict:
    """
    读取指定日早盘文案与强势选拔结果。

    @param db: 会话
    @param asof: 业务日
    """
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
            "strategy_id": pick.strategy_id or None,
        }
        if pick.pick_type == "board":
            boards.append(item)
        else:
            stocks.append(item)
    return {
        "asof": asof.isoformat(),
        "briefs": by_stage,
        "boards": boards,
        "stocks": stocks,
        "research_picks": list_research_picks(db, asof, "morning"),
    }


@router.post("/preopen")
def preopen(asof: date | None = None, db: Session = Depends(get_db)):
    """开盘前篇；休息日自动按上一交易日。"""
    return MorningBriefService(db).run_preopen(asof).model_dump()


@router.post("/post-auction")
def post_auction(asof: date | None = None, db: Session = Depends(get_db)):
    """
    竞价选拔：若当日尚无快照则先从行情源拉取自选竞价快照。

    休息日先解析为上一交易日，再拉快照 / 选拔。
    """
    svc = MorningBriefService(db)
    asof, _note = svc.resolve_asof(asof)
    try:
        AuctionSnapshotIngestor(
            db, _get_market_data(), asof=asof, scope="listed"
        ).run()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return svc.run_post_auction(asof).model_dump()


@router.get("/latest")
def morning_latest(asof: date | None = None, db: Session = Depends(get_db)):
    """
    读取当日早盘文案与强势选拔结果。

    非交易日直接读上一交易日（避免休息日残留的「跳过」摘要挡住真实结果）。

    @param asof: 交易日，默认今天
    """
    asof = asof or date.today()
    cal = CalendarService(db)
    if not cal.is_trade_day(asof):
        asof = cal.previous_trade_day(asof)
    return _latest_payload(db, asof)


@router.get("/history")
def morning_history(asof: date | None = None, db: Session = Depends(get_db)):
    """
    指定日历史结果（与 latest 同形，不做交易日回退）。

    @param asof: 业务日，缺省今天
    """
    asof = asof or date.today()
    return _latest_payload(db, asof)


@router.post("/research-refine")
def research_refine(body: ResearchRefineIn | None = None, db: Session = Depends(get_db)):
    """
    投研精选：对当日早盘候选打分取 TopN。

    @param body: 可选 asof / top_n / min_confidence
    """
    payload = body or ResearchRefineIn()
    report = ResearchRefineService(db).run(
        "morning",
        payload.asof,
        top_n=payload.top_n,
        min_confidence=payload.min_confidence,
    )
    db.commit()
    return report.model_dump()


@router.post("/bind")
def morning_bind(body: MorningBindIn | None = None, db: Session = Depends(get_db)):
    """
    早盘强势个股（或指定 symbols）一键写入自选。
    """
    payload = body or MorningBindIn()
    asof = payload.asof
    if asof is None:
        asof, _ = MorningBriefService(db).resolve_asof()
    return bind_morning_picks(
        db,
        asof=asof,
        limit=payload.limit,
        symbols=payload.symbols,
    )
