"""行情 / 自选 / 板块 / jobs / bars。"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_db.models import BarMinute
from desk_market import MarketService
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import MockQmtMarketData, XtdataMarketData

router = APIRouter(prefix="/market")


class WatchIn(BaseModel):
    symbol: str
    name: str = ""


def get_market_data():
    """默认行情源：优先 xtdata，失败则空 Mock。"""
    try:
        return XtdataMarketData()
    except Exception:  # noqa: BLE001
        return MockQmtMarketData(instruments=[])


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    return MarketService(db).list_watchlist()


@router.post("/watchlist")
def add_watch(body: WatchIn, db: Session = Depends(get_db)):
    return MarketService(db).add_watchlist(body.symbol, body.name)


@router.get("/boards")
def boards(board_type: str | None = None, db: Session = Depends(get_db)):
    return MarketService(db).list_boards(board_type)


@router.get("/bars/daily")
def bars_daily(
    symbol: str,
    from_: date = Query(alias="from"),
    to: date = Query(...),
    adj: str | None = None,
    db: Session = Depends(get_db),
):
    """读库日线；adj=None/qfq→前复权默认列，hfq→后复权映射。"""
    df = MarketService(db).load_daily_df(symbol, from_, to, adj=adj)
    return df.to_dict(orient="records")


@router.get("/bars/minute")
def bars_minute(
    symbol: str,
    from_: str = Query(alias="from"),
    to: str = Query(...),
    db: Session = Depends(get_db),
):
    """读库分钟线。"""
    start = datetime.fromisoformat(from_)
    end = datetime.fromisoformat(to)
    from desk_common.symbols import normalize_symbol

    sym = normalize_symbol(symbol)
    rows = db.scalars(
        select(BarMinute)
        .where(BarMinute.symbol == sym, BarMinute.ts >= start, BarMinute.ts <= end)
        .order_by(BarMinute.ts)
    ).all()
    return [
        {
            "ts": r.ts.isoformat(),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "amount": r.amount,
        }
        for r in rows
    ]


@router.get("/intraday/quote")
def intraday_quote(symbols: str, db: Session = Depends(get_db)):
    """
    盘中报价：直连行情源快照（可不落库）。

    @param symbols: 逗号分隔
    """
    _ = db
    md = get_market_data()
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    return md.get_snapshots(syms)


@router.get("/jobs/status")
def jobs_status(db: Session = Depends(get_db)):
    return MarketJobs(db, md=get_market_data()).recent_status()


@router.post("/jobs/daily-sync")
def jobs_daily_sync(db: Session = Depends(get_db)):
    out = MarketJobs(db, md=get_market_data()).ingest_daily_incremental()
    return out


@router.post("/jobs/minute-sync")
def jobs_minute_sync(db: Session = Depends(get_db)):
    return MarketJobs(db, md=get_market_data()).ingest_minute_watch()


@router.post("/jobs/backfill")
def jobs_backfill(db: Session = Depends(get_db)):
    return MarketJobs(db, md=get_market_data()).backfill_daily_chunks()
