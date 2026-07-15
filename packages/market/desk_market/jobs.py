"""行情任务编排入口。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from desk_calendar import CalendarService, CalendarSync
from desk_market.akshare_daily import AkshareDailyClient
from desk_market.config import MarketSyncConfig, load_indices, load_market_sync_config
from desk_market.daily_ingest import DailyBarIngestor
from desk_market.history_backfill import HistoryBackfill
from desk_market.job_store import JobStore
from desk_market.minute_ingest import MinuteBarIngestor
from desk_market.qmt_md import QmtMarketData
from desk_market.security_universe import SecurityListSync


class _WeekendCalendarClient:
    """无外部源时用周末规则填充一段日历。"""

    def trade_days(self, start: date, end: date) -> list[tuple[date, bool]]:
        out: list[tuple[date, bool]] = []
        d = start
        while d <= end:
            out.append((d, d.weekday() < 5))
            d += timedelta(days=1)
        return out


class MarketJobs:
    """统一任务入口：可观测成功/失败。"""

    def __init__(
        self,
        db: Session,
        md: QmtMarketData,
        akshare: Any | None = None,
        config: MarketSyncConfig | None = None,
        calendar_client: Any | None = None,
    ) -> None:
        self.db = db
        self.md = md
        self.akshare = akshare if akshare is not None else AkshareDailyClient()
        self.config = config or load_market_sync_config()
        self.calendar_client = calendar_client or _WeekendCalendarClient()
        self.store = JobStore(db)

    def recent_status(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近任务状态。"""
        return self.store.recent(limit)

    def sync_trade_calendar(self, start: date | None = None, end: date | None = None) -> dict[str, Any]:
        """同步交易日历。"""
        row = self.store.start("sync_trade_calendar")
        try:
            today = date.today()
            start = start or date(today.year, 1, 1)
            end = end or date(today.year, 12, 31)
            n = CalendarSync(self.db, self.calendar_client).run(start, end)
            self.store.finish(row, status="ok", message=f"upserted={n}")
            return {"status": "ok", "upserted": n}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc)}

    def sync_security_list(self) -> dict[str, Any]:
        """同步证券列表。"""
        row = self.store.start("sync_security_list")
        try:
            universe = SecurityListSync(self.db, self.md).run()
            self.store.finish(row, status="ok", symbols_done=len(universe))
            return {"status": "ok", "universe_size": len(universe)}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc)}

    def ingest_daily_incremental(self, asof: date | None = None) -> dict[str, Any]:
        """日终近 N 日增量。"""
        row = self.store.start("ingest_daily_incremental")
        asof = asof or date.today()
        try:
            if not CalendarService(self.db).require_trade_day(asof):
                self.store.finish(row, status="ok", message="skipped_non_trade_day")
                return {"status": "ok", "skipped": True}
            result = DailyBarIngestor(
                self.db,
                self.md,
                incremental_days=self.config.incremental_days,
                asof=asof,
                daily_start_date=self.config.daily_start_date,
            ).run()
            if result.get("errors") and result.get("symbols_done", 0) == 0:
                err = "; ".join(result["errors"])[:500]
                self.store.finish(row, status="failed", error_summary=err, symbols_done=0)
                return {"status": "failed", "errors": result["errors"]}
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("symbols_done", 0)),
                message="; ".join(result.get("errors") or [])[:500],
            )
            return {"status": "ok", **result}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc)}

    def backfill_daily_chunks(self, asof: date | None = None) -> dict[str, Any]:
        """历史缺口回填。"""
        row = self.store.start("backfill_daily_chunks")
        try:
            result = HistoryBackfill(
                self.db,
                self.md,
                akshare=self.akshare,
                daily_start_date=self.config.daily_start_date,
                asof=asof or date.today(),
            ).run()
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("symbols_done", 0)),
                message="; ".join(result.get("errors") or [])[:500],
            )
            return {"status": "ok", **result}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc)}

    def ingest_minute_watch(self, asof: date | None = None) -> dict[str, Any]:
        """自选∪指数分钟同步。"""
        row = self.store.start("ingest_minute_watch")
        try:
            result = MinuteBarIngestor(
                self.db,
                self.md,
                index_symbols=load_indices(),
                asof=asof or date.today(),
                purge=True,
            ).run()
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("bars_written", 0)),
                message=f"purged={result.get('purged', 0)}",
            )
            return {"status": "ok", **result}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc)}
