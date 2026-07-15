"""scheduler 工厂注册任务 ID。"""

from desk_market.scheduler import build_market_scheduler


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
    }
    assert expected <= set(job_ids)
    if sched.running:
        sched.shutdown(wait=False)
