"""Paper Runner 定时调度（APScheduler）。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from desk_common.settings import get_settings
from desk_db import get_session_factory
from desk_market.scheduler import within_a_share_session

logger = logging.getLogger(__name__)
_BJ = ZoneInfo("Asia/Shanghai")

# 最近一次调度结果（进程内，供 API 查询）
_LAST_RUN: dict[str, Any] = {
    "at": None,
    "strategy_id": None,
    "status": "idle",
    "filled": 0,
    "count": 0,
    "message": "",
}


def get_runner_status() -> dict[str, Any]:
    """Runner 调度状态。"""
    s = get_settings()
    return {
        "enabled": bool(s.paper_runner_enabled),
        "strategy_id": s.paper_runner_strategy_id,
        "interval_minutes": int(s.paper_runner_interval_minutes),
        "session_only": True,
        "last_run": dict(_LAST_RUN),
        "in_session": within_a_share_session(),
    }


def _execute_watchlist_run() -> None:
    """开 Session 跑自选 Paper Runner。"""
    settings = get_settings()
    if not settings.paper_runner_enabled:
        return
    if not within_a_share_session():
        return
    strategy_id = (settings.paper_runner_strategy_id or "ma_cross").strip()
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        from desk_broker.paper_runner import PaperStrategyRunner

        out = PaperStrategyRunner(db).run_watchlist(strategy_id=strategy_id)
        db.commit()
        _LAST_RUN.update(
            {
                "at": datetime.now(_BJ).isoformat(),
                "strategy_id": strategy_id,
                "status": out.get("status", "ok"),
                "filled": int(out.get("filled") or 0),
                "count": int(out.get("count") or 0),
                "message": f"watchlist scan {out.get('count', 0)} symbols",
            }
        )
        logger.info(
            "paper_runner: strategy=%s count=%s filled=%s",
            strategy_id,
            out.get("count"),
            out.get("filled"),
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _LAST_RUN.update(
            {
                "at": datetime.now(_BJ).isoformat(),
                "strategy_id": strategy_id,
                "status": "error",
                "filled": 0,
                "count": 0,
                "message": str(exc),
            }
        )
        logger.exception("paper_runner scheduled run failed")
    finally:
        db.close()


def build_paper_runner_scheduler(
    *,
    enabled: bool | None = None,
    dry_run: bool = False,
) -> tuple[BackgroundScheduler, list[str]]:
    """
    创建 Paper Runner 调度器。

    连续竞价时段按间隔扫描自选；另在 15:35 再跑一次（日线收盘后）。

    @param enabled: 覆盖 Settings.paper_runner_enabled；None 则读配置
    @param dry_run: 仅注册占位 job
    """
    settings = get_settings()
    on = settings.paper_runner_enabled if enabled is None else enabled
    sched = BackgroundScheduler(timezone=_BJ)
    job_ids: list[str] = []
    if not on:
        return sched, job_ids

    minutes = max(5, int(settings.paper_runner_interval_minutes or 30))

    if dry_run:
        sched.add_job(lambda: None, "interval", minutes=minutes, id="paper_runner_interval")
        sched.add_job(lambda: None, CronTrigger(hour=15, minute=35, day_of_week="mon-fri", timezone=_BJ), id="paper_runner_close")
        return sched, ["paper_runner_interval", "paper_runner_close"]

    sched.add_job(
        _execute_watchlist_run,
        IntervalTrigger(minutes=minutes, timezone=_BJ),
        id="paper_runner_interval",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    job_ids.append("paper_runner_interval")

    # 收盘后补跑（日线策略）
    sched.add_job(
        _execute_watchlist_run,
        CronTrigger(hour=15, minute=35, day_of_week="mon-fri", timezone=_BJ),
        id="paper_runner_close",
        replace_existing=True,
        max_instances=1,
    )
    job_ids.append("paper_runner_close")
    return sched, job_ids
