"""scheduler 工厂注册任务 ID 与分钟同步时段门闸。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from desk_market.scheduler import build_market_scheduler, within_a_share_session

_BJ = ZoneInfo("Asia/Shanghai")


def test_build_scheduler_registers_job_ids():
    sched, job_ids = build_market_scheduler(enabled=True, dry_run=True)
    expected = {
        "sync_trade_calendar",
        "sync_security_list",
        "ingest_daily_incremental",
        "backfill_daily_chunks",
        "ingest_minute_watch",
        "sync_sentiment_daily",
        "sync_lhb_daily",
        "run_morning_preopen",
        "ingest_auction_snapshots",
        "run_morning_post_auction",
    }
    assert expected <= set(job_ids)
    if sched.running:
        sched.shutdown(wait=False)


def test_within_a_share_session_beijing_hours():
    assert within_a_share_session(datetime(2024, 7, 15, 9, 30, tzinfo=_BJ)) is True  # Mon
    assert within_a_share_session(datetime(2024, 7, 15, 10, 0, tzinfo=_BJ)) is True
    assert within_a_share_session(datetime(2024, 7, 15, 11, 30, tzinfo=_BJ)) is True
    assert within_a_share_session(datetime(2024, 7, 15, 12, 0, tzinfo=_BJ)) is False
    assert within_a_share_session(datetime(2024, 7, 15, 13, 0, tzinfo=_BJ)) is True
    assert within_a_share_session(datetime(2024, 7, 15, 15, 0, tzinfo=_BJ)) is True
    assert within_a_share_session(datetime(2024, 7, 15, 15, 1, tzinfo=_BJ)) is False
    assert within_a_share_session(datetime(2024, 7, 15, 20, 0, tzinfo=_BJ)) is False
    assert within_a_share_session(datetime(2024, 7, 13, 10, 0, tzinfo=_BJ)) is False  # Sat


def test_minute_job_uses_session_only_wrapper():
    """分钟任务在配置 session_only 时挂的是带时段门闸的回调。"""
    from desk_market import scheduler as sch

    sched, _ = build_market_scheduler(enabled=True, dry_run=False)
    job = sched.get_job("ingest_minute_watch")
    assert job is not None
    assert job.func is sch._run_job_session_only
    daily = sched.get_job("ingest_daily_incremental")
    assert daily is not None
    assert daily.func is sch._run_job
    if sched.running:
        sched.shutdown(wait=False)
