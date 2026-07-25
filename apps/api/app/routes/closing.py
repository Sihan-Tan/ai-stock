"""尾盘选股。"""

from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_closing_pick import ClosingPickService
from desk_closing_pick.bind import bind_closing_picks
from desk_db import get_db
from desk_db.models import ClosingBriefRow, ClosingPick
from desk_strategy import StrategyRegistry, strategy_has_closing_role

router = APIRouter(prefix="/closing")


class ClosingRunIn(BaseModel):
    """手动跑尾盘选股。"""

    asof: date | None = None
    strategy_ids: list[str] | None = None


class ClosingBindIn(BaseModel):
    """尾盘命中写入自选。"""

    asof: date | None = None
    limit: int = Field(20, ge=1, le=100)
    symbols: list[str] | None = None
    strategy_ids: list[str] | None = None


class ClosingMarkIn(BaseModel):
    """开关策略 closing 角色。"""

    strategy_id: str
    closing: bool = True


def _latest_payload(db: Session, asof: date) -> dict:
    """
    读取指定日 brief + stocks，形状对齐 morning_latest。

    @param db: 会话
    @param asof: 交易日
    """
    briefs = db.scalars(
        select(ClosingBriefRow)
        .where(ClosingBriefRow.asof == asof)
        .order_by(ClosingBriefRow.id.desc())
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
        select(ClosingPick)
        .where(ClosingPick.asof == asof)
        .order_by(ClosingPick.score.desc())
    ).all()
    stocks = []
    for pick in picks:
        try:
            meta = json.loads(pick.meta_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        stocks.append(
            {
                "code": pick.code,
                "name": pick.name,
                "score": pick.score,
                **meta,
                "strategy_id": pick.strategy_id,
            }
        )
    return {"asof": asof.isoformat(), "briefs": by_stage, "stocks": stocks}


@router.post("/run")
def closing_run(body: ClosingRunIn | None = None, db: Session = Depends(get_db)):
    """
    跑尾盘选股；空 strategy_ids 则用全部 closing 角色策略。
    """
    payload = body or ClosingRunIn()
    return ClosingPickService(db).run(
        asof=payload.asof, strategy_ids=payload.strategy_ids
    ).model_dump()


@router.get("/latest")
def closing_latest(asof: date | None = None, db: Session = Depends(get_db)):
    """
    读取当日尾盘文案与命中结果。

    @param asof: 交易日，默认今天
    """
    asof = asof or date.today()
    return _latest_payload(db, asof)


@router.get("/history")
def closing_history(asof: date | None = None, db: Session = Depends(get_db)):
    """
    指定日历史结果（与 latest 同形）。

    @param asof: 交易日，缺省今天
    """
    asof = asof or date.today()
    return _latest_payload(db, asof)


@router.post("/bind")
def closing_bind(body: ClosingBindIn | None = None, db: Session = Depends(get_db)):
    """
    尾盘命中个股（或指定 symbols）一键写入自选。
    """
    payload = body or ClosingBindIn()
    return bind_closing_picks(
        db,
        asof=payload.asof,
        limit=payload.limit,
        symbols=payload.symbols,
        strategy_ids=payload.strategy_ids,
    )


@router.get("/strategies")
def closing_strategies(db: Session = Depends(get_db)):
    """列出非 archived 策略及 closing 角色标记。"""
    out = []
    for m in StrategyRegistry(db).list(include_archived=False):
        data = m.model_dump()
        data["closing"] = strategy_has_closing_role(m.params)
        out.append(data)
    return out


@router.post("/strategies/mark")
def closing_strategies_mark(body: ClosingMarkIn, db: Session = Depends(get_db)):
    """
    开关策略 params.roles 中的 closing。

    @param body: strategy_id + closing
    """
    meta = StrategyRegistry(db).set_closing_role(body.strategy_id, body.closing)
    if meta is None:
        raise HTTPException(404, f"strategy not found: {body.strategy_id}")
    data = meta.model_dump()
    data["closing"] = strategy_has_closing_role(meta.params)
    return data
