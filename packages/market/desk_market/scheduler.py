"""APScheduler 注册行情任务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from desk_db import get_session_factory
from desk_market.config import load_market_sync_config
from desk_market.jobs import MarketJobs
from desk_market.qmt_md import MockQmtMarketData, XtdataMarketData

_BJ = ZoneInfo("Asia/Shanghai")


def within_a_share_session(now: datetime | None = None) -> bool:
    """
    是否处于 A 股连续竞价时段（北京时间）。

    交易日 09:30–11:30、13:00–15:00（含边界）。周六日为 False。
    仅用于调度门闸；手动 API 触发不经过此函数。

    @param now: 可选时点；默认当前北京时间
    """
    if now is None:
        now = datetime.now(_BJ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=_BJ)
    else:
        now = now.astimezone(_BJ)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    morning = 9 * 60 + 30 <= minutes <= 11 * 60 + 30
    afternoon = 13 * 60 <= minutes <= 15 * 60
    return morning or afternoon


def _build_md():
    """优先真实 xtdata，失败则 Mock（调度仍可启动，任务会记失败）。"""
    try:
        return XtdataMarketData()
    except Exception:  # noqa: BLE001
        return MockQmtMarketData(instruments=[])


def _run_job(method_name: str) -> None:
    """开 Session 执行 MarketJobs 方法并 commit。"""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        jobs = MarketJobs(db, md=_build_md())
        getattr(jobs, method_name)()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        raise
    finally:
        db.close()


def _run_job_session_only(method_name: str) -> None:
    """仅在连续竞价时段执行；盘后跳过（不写 Job 记录）。"""
    if not within_a_share_session():
        return
    _run_job(method_name)


def build_market_scheduler(
    enabled: bool = True,
    dry_run: bool = False,
) -> tuple[BackgroundScheduler, list[str]]:
    """
    创建并注册行情调度器。

    @param enabled: False 时不注册任务
    @param dry_run: True 时仅注册占位函数，不触真实 DB（测 job id）
    @returns: (scheduler, job_ids)
    """
    sched = BackgroundScheduler()
    job_ids: list[str] = []
    if not enabled:
        return sched, job_ids

    cfg = load_market_sync_config()
    jobs_cfg: dict[str, Any] = cfg.jobs or {}

    def _add(job_id: str, method: str) -> None:
        spec = jobs_cfg.get(job_id) or {}
        if dry_run:
            sched.add_job(lambda: None, "interval", seconds=3600, id=job_id, replace_existing=True)
        elif "minutes" in spec:
            session_only = bool(spec.get("session_only", False))
            target = _run_job_session_only if session_only else _run_job
            sched.add_job(
                target,
                IntervalTrigger(minutes=int(spec["minutes"])),
                args=[method],
                id=job_id,
                replace_existing=True,
            )
        else:
            cron = str(spec.get("cron", "0 2 * * *")).split()
            if len(cron) >= 5:
                trigger = CronTrigger(
                    minute=cron[0],
                    hour=cron[1],
                    day=cron[2],
                    month=cron[3],
                    day_of_week=cron[4],
                    timezone=_BJ,
                )
            else:
                trigger = CronTrigger(hour=2, minute=0, timezone=_BJ)
            sched.add_job(_run_job, trigger, args=[method], id=job_id, replace_existing=True)
        job_ids.append(job_id)

    _add("sync_trade_calendar", "sync_trade_calendar")
    _add("sync_security_list", "sync_security_list")
    _add("ingest_daily_incremental", "ingest_daily_incremental")
    _add("backfill_daily_chunks", "backfill_daily_chunks")
    _add("ingest_minute_watch", "ingest_minute_watch")
    _add("sync_sentiment_daily", "sync_sentiment_daily")
    _add("sync_lhb_daily", "sync_lhb_daily")
    return sched, job_ids
