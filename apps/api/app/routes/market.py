"""行情 / 自选 / 板块 / jobs / bars。"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db import get_db, get_session_factory
from desk_db.models import BarMinute
from desk_market import MarketService
from desk_market.job_store import JobStore
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import MockQmtMarketData, XtdataMarketData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market")

# 可后台入队的任务名 → MarketJobs 方法名
_ENQUEUEABLE: dict[str, str] = {
    "sync_trade_calendar": "sync_trade_calendar",
    "sync_security_list": "sync_security_list",
    "ingest_daily_incremental": "ingest_daily_incremental",
    "backfill_daily_chunks": "backfill_daily_chunks",
    "ingest_minute_watch": "ingest_minute_watch",
}


class WatchIn(BaseModel):
    symbol: str
    name: str = ""


def get_market_data():
    """默认行情源：优先 xtdata，失败则空 Mock。"""
    try:
        return XtdataMarketData()
    except Exception:  # noqa: BLE001
        return MockQmtMarketData(instruments=[])


def _run_market_job(job_id: str, run_id: int) -> None:
    """
    BackgroundTasks 执行体：独立 Session，结束后 commit。

    @param job_id: 任务逻辑名
    @param run_id: 已创建的 MarketJobRun.id
    """
    method = _ENQUEUEABLE.get(job_id)
    if not method:
        return
    db = get_session_factory()()
    try:
        jobs = MarketJobs(db, md=get_market_data())
        getattr(jobs, method)(run_id=run_id)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("background job failed job_id=%s run_id=%s", job_id, run_id)
        db.rollback()
        try:
            store = JobStore(db)
            row = store.get(run_id)
            if row is not None and row.status == "running":
                store.finish(row, status="failed", error_summary=str(exc)[:500])
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()


def _enqueue(job_id: str, db: Session, background_tasks: BackgroundTasks) -> dict:
    """创建 running 记录并入队，立即返回 run_id。"""
    store = JobStore(db)
    if store.has_running(job_id):
        raise HTTPException(status_code=409, detail=f"{job_id} already running")
    row = store.start(job_id)
    db.commit()
    background_tasks.add_task(_run_market_job, job_id, row.id)
    return {"run_id": row.id, "job_id": job_id, "status": "running"}


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    return MarketService(db).list_watchlist()


@router.post("/watchlist")
def add_watch(body: WatchIn, db: Session = Depends(get_db)):
    return MarketService(db).add_watchlist(body.symbol, body.name)


@router.get("/boards")
def boards(board_type: str | None = None, db: Session = Depends(get_db)):
    return MarketService(db).list_boards(board_type)


@router.get("/stock/{symbol}/meta")
def stock_meta(symbol: str, db: Session = Depends(get_db)):
    """单标的元数据。"""
    from desk_market.stock_detail import get_security_meta

    data = get_security_meta(db, symbol)
    if data is None:
        raise HTTPException(status_code=404, detail="symbol not found")
    return data


@router.get("/stock/{symbol}/boards")
def stock_boards(symbol: str, db: Session = Depends(get_db)):
    """单标的所属板块/概念。"""
    from desk_market.stock_detail import list_boards_for_symbol

    return {"symbol": symbol, "boards": list_boards_for_symbol(db, symbol)}


@router.get("/bars/daily")
def bars_daily(
    symbol: str,
    from_: date = Query(alias="from"),
    to: date = Query(...),
    adj: str | None = None,
    period: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    读库日线；可选聚合成周/月。

    @param symbol: 标的
    @param from_: 起始日
    @param to: 结束日
    @param adj: 复权；None/qfq→前复权，hfq→后复权
    @param period: day|week|month；week/month 时对日线聚合
    """
    df = MarketService(db).load_daily_df(symbol, from_, to, adj=adj)
    if period in ("week", "month"):
        from desk_market.stock_detail import aggregate_ohlcv

        df = aggregate_ohlcv(df, period)
    return df.to_dict(orient="records")


@router.get("/stock/{symbol}/technicals")
def stock_technicals(symbol: str, db: Session = Depends(get_db)):
    """单标的技术指标（MA / MACD / RSI）。"""
    from desk_market.stock_detail import compute_technicals

    try:
        return compute_technicals(db, symbol)
    except Exception as exc:  # noqa: BLE001
        logger.exception("technicals failed %s", symbol)
        return {"available": False, "symbol": symbol, "error": str(exc)[:200]}


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
def jobs_status(limit: int = 30, db: Session = Depends(get_db)):
    return MarketJobs(db, md=get_market_data()).recent_status(limit=limit)


@router.get("/jobs/{run_id}")
def job_detail(run_id: int, db: Session = Depends(get_db)):
    detail = MarketJobs(db, md=get_market_data()).get_run(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@router.post("/jobs/calendar-sync")
def jobs_calendar_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _enqueue("sync_trade_calendar", db, background_tasks)


@router.post("/jobs/security-list")
def jobs_security_list(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _enqueue("sync_security_list", db, background_tasks)


@router.post("/jobs/daily-sync")
def jobs_daily_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _enqueue("ingest_daily_incremental", db, background_tasks)


@router.post("/jobs/minute-sync")
def jobs_minute_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _enqueue("ingest_minute_watch", db, background_tasks)


@router.post("/jobs/backfill")
def jobs_backfill(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _enqueue("backfill_daily_chunks", db, background_tasks)
