"""复盘自动任务调度（交易日 15:45）。"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from desk_common.settings import get_settings
from desk_db import get_session_factory

logger = logging.getLogger(__name__)
_BJ = ZoneInfo("Asia/Shanghai")

_LAST_RUN: dict[str, Any] = {
    "at": None,
    "status": "idle",
    "message": "",
}


def get_review_scheduler_status() -> dict[str, Any]:
    """复盘自动调度状态。"""
    s = get_settings()
    return {
        "enabled": bool(s.review_auto),
        "cron": "15:45 Mon-Fri Asia/Shanghai",
        "last_run": dict(_LAST_RUN),
    }


def _execute_auto_review() -> None:
    """定时入口：检查开关后生成。"""
    settings = get_settings()
    if not settings.review_auto:
        return
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        from desk_review.generate import maybe_auto_review

        asof = datetime.now(_BJ).date()
        out = maybe_auto_review(db, asof) or {"status": "noop"}
        db.commit()
        _LAST_RUN.update(
            {
                "at": datetime.now(_BJ).isoformat(),
                "status": out.get("status", "ok"),
                "message": str(out.get("reason") or out.get("error") or out.get("asof") or ""),
            }
        )
        logger.info("auto review asof=%s status=%s", asof, out.get("status"))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _LAST_RUN.update(
            {
                "at": datetime.now(_BJ).isoformat(),
                "status": "error",
                "message": str(exc),
            }
        )
        logger.exception("auto review scheduled run failed")
    finally:
        db.close()


def build_review_scheduler(*, dry_run: bool = False) -> tuple[BackgroundScheduler, list[str]]:
    """注册交易日 15:45 复盘 job（开关在任务内检查，便于热切换）。"""
    sched = BackgroundScheduler(timezone=_BJ)
    trigger = CronTrigger(hour=15, minute=45, day_of_week="mon-fri", timezone=_BJ)
    if dry_run:
        sched.add_job(lambda: None, trigger, id="review_auto_close")
        return sched, ["review_auto_close"]
    sched.add_job(
        _execute_auto_review,
        trigger,
        id="review_auto_close",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return sched, ["review_auto_close"]
