"""行情任务编排入口。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from desk_calendar import CalendarService, CalendarSync
from desk_db.models import MarketJobRun
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
        sentiment_client: Any | None = None,
        lhb_client: Any | None = None,
    ) -> None:
        self.db = db
        self.md = md
        self.akshare = akshare if akshare is not None else AkshareDailyClient()
        self.config = config or load_market_sync_config()
        self.calendar_client = calendar_client or _WeekendCalendarClient()
        self.sentiment_client = sentiment_client
        self.lhb_client = lhb_client
        self.store = JobStore(db)

    def recent_status(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近任务状态。"""
        return self.store.recent(limit)

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        """单次运行详情。"""
        row = self.store.get(run_id)
        return JobStore.to_dict(row) if row else None

    def _begin(self, job_id: str, run_id: int | None) -> MarketJobRun:
        """取得已有 run 或新建。"""
        if run_id is not None:
            row = self.store.get(run_id)
            if row is None:
                raise ValueError(f"unknown_run_id={run_id}")
            return row
        return self.store.start(job_id)

    def _on_progress(self, row: MarketJobRun) -> Callable[[int, str], None]:
        """中间进度回调（提交后供轮询读取）。"""

        def _cb(symbols_done: int, message: str = "") -> None:
            self.store.progress(row, symbols_done=symbols_done, message=message)

        return _cb

    def sync_trade_calendar(
        self,
        start: date | None = None,
        end: date | None = None,
        *,
        run_id: int | None = None,
    ) -> dict[str, Any]:
        """同步交易日历。"""
        row = self._begin("sync_trade_calendar", run_id)
        try:
            today = date.today()
            start = start or date(today.year, 1, 1)
            end = end or date(today.year, 12, 31)
            n = CalendarSync(self.db, self.calendar_client).run(start, end)
            self.store.finish(row, status="ok", message=f"upserted={n}")
            return {"status": "ok", "upserted": n, "run_id": row.id}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}

    def sync_security_list(self, *, run_id: int | None = None) -> dict[str, Any]:
        """同步证券列表。"""
        row = self._begin("sync_security_list", run_id)
        try:
            universe = SecurityListSync(self.db, self.md).run()
            self.store.finish(row, status="ok", symbols_done=len(universe))
            return {"status": "ok", "universe_size": len(universe), "run_id": row.id}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}

    def ingest_daily_incremental(
        self, asof: date | None = None, *, run_id: int | None = None
    ) -> dict[str, Any]:
        """日终近 N 日增量。"""
        row = self._begin("ingest_daily_incremental", run_id)
        asof = asof or date.today()
        try:
            if not CalendarService(self.db).require_trade_day(asof):
                self.store.finish(row, status="ok", message="skipped_non_trade_day")
                return {"status": "ok", "skipped": True, "run_id": row.id}
            result = DailyBarIngestor(
                self.db,
                self.md,
                incremental_days=self.config.incremental_days,
                asof=asof,
                daily_start_date=self.config.daily_start_date,
            ).run(on_progress=self._on_progress(row))
            if result.get("errors") and result.get("symbols_done", 0) == 0:
                err = "; ".join(result["errors"])[:500]
                self.store.finish(row, status="failed", error_summary=err, symbols_done=0)
                return {"status": "failed", "errors": result["errors"], "run_id": row.id}
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("symbols_done", 0)),
                message="; ".join(result.get("errors") or [])[:500],
            )
            return {"status": "ok", **result, "run_id": row.id}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}

    def backfill_daily_chunks(
        self, asof: date | None = None, *, run_id: int | None = None
    ) -> dict[str, Any]:
        """历史缺口回填。"""
        row = self._begin("backfill_daily_chunks", run_id)
        try:
            result = HistoryBackfill(
                self.db,
                self.md,
                akshare=self.akshare,
                daily_start_date=self.config.daily_start_date,
                asof=asof or date.today(),
            ).run(on_progress=self._on_progress(row))
            err_tail = "; ".join(result.get("errors") or [])
            msg = f"refill_incomplete={result.get('refill_incomplete', 0)}"
            if err_tail:
                msg = f"{msg}; {err_tail}"
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("symbols_done", 0)),
                message=msg[:500],
            )
            return {"status": "ok", **result, "run_id": row.id}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}

    def ingest_minute_watch(
        self, asof: date | None = None, *, run_id: int | None = None
    ) -> dict[str, Any]:
        """自选∪指数分钟同步。"""
        row = self._begin("ingest_minute_watch", run_id)
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
            return {"status": "ok", **result, "run_id": row.id}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}

    def _resolve_sentiment_client(self):
        if self.sentiment_client is not None:
            return self.sentiment_client
        primary = None
        try:
            from desk_sentiment import XtdataSentimentClient

            primary = XtdataSentimentClient()
        except Exception:  # noqa: BLE001
            primary = None
        try:
            from desk_sentiment.akshare_client import AkshareSentimentClient

            secondary = AkshareSentimentClient()
        except Exception:  # noqa: BLE001
            secondary = None

        if primary is not None and secondary is not None:
            from desk_sentiment.akshare_client import FallbackSentimentClient

            # AkShare 涨停池优先（快）；xtdata 作次选
            return FallbackSentimentClient(secondary, primary)
        if secondary is not None:
            return secondary
        if primary is not None:
            return primary
        from desk_sentiment import MockQmtSentimentClient

        return MockQmtSentimentClient([])

    def _resolve_lhb_client(self):
        if self.lhb_client is not None:
            return self.lhb_client
        from desk_lhb import AkshareLhbClient

        return AkshareLhbClient()

    def sync_sentiment_daily(self, asof: date | None = None) -> dict[str, Any]:
        """日终打板情绪。"""
        from desk_common.beijing_time import beijing_today
        from desk_sentiment import SentimentDailyIngestor

        row = self.store.start("sync_sentiment_daily")
        asof = asof or beijing_today()
        try:
            if not CalendarService(self.db).require_trade_day(asof):
                self.store.finish(row, status="ok", message="skipped_non_trade_day")
                return {"status": "ok", "skipped": True, "asof": asof.isoformat()}
            client = self._resolve_sentiment_client()
            from sqlalchemy import select

            from desk_db.models import SecurityMeta
            from desk_sentiment.akshare_client import AkshareSentimentClient, FallbackSentimentClient

            listed = self.db.scalars(
                select(SecurityMeta).where(SecurityMeta.is_delisted.is_(False))
            ).all()
            if listed:
                symbols = [r.symbol for r in listed]
            else:
                symbols = self.md.list_a_share_symbols(include_delisted=False)
            # 涨停池源不按全市场过滤，避免 BJ/代码格式误杀
            ingest_symbols: list[str] | None
            if isinstance(client, (AkshareSentimentClient, FallbackSentimentClient)):
                ingest_symbols = None
            else:
                ingest_symbols = symbols or None
            result = SentimentDailyIngestor(
                self.db, client, asof=asof, symbols=ingest_symbols
            ).run()
            cover = int(result.get("cover") or 0)
            skipped_write = bool(result.get("skipped_write"))
            msg = f"cover={cover}"
            if skipped_write or cover == 0:
                msg = f"{msg}; empty_source（未覆盖库内快照；请检查网络/AkShare 或 QMT）"
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("symbols_done", 0)),
                message=msg,
            )
            return {
                "status": "ok",
                "asof": asof.isoformat(),
                **result,
                "empty_source": skipped_write or cover == 0,
            }
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "asof": asof.isoformat()}

    def sync_lhb_daily(self, asof: date | None = None) -> dict[str, Any]:
        """日终龙虎榜。"""
        from desk_lhb import LhbDailyIngestor

        row = self.store.start("sync_lhb_daily")
        asof = asof or date.today()
        try:
            if not CalendarService(self.db).require_trade_day(asof):
                self.store.finish(row, status="ok", message="skipped_non_trade_day")
                return {"status": "ok", "skipped": True}
            client = self._resolve_lhb_client()
            result = LhbDailyIngestor(self.db, client, asof=asof).run()
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("symbols_done", 0)),
                message=f"seats={result.get('seats')}",
            )
            return {"status": "ok", **result}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc)}

    def ingest_auction_snapshots(
        self, asof: date | None = None, *, run_id: int | None = None
    ) -> dict[str, Any]:
        """集合竞价快照落库（自选宇宙）。"""
        from desk_market.auction_ingest import AuctionSnapshotIngestor

        row = self._begin("ingest_auction_snapshots", run_id)
        asof = asof or date.today()
        try:
            if not CalendarService(self.db).require_trade_day(asof):
                self.store.finish(row, status="ok", message="skipped_non_trade_day")
                return {"status": "ok", "skipped": True, "run_id": row.id}
            result = AuctionSnapshotIngestor(self.db, self.md, asof=asof).run()
            self.store.finish(
                row,
                status="ok",
                symbols_done=int(result.get("written", 0)),
                message=f"skipped={result.get('skipped', 0)}",
            )
            return {"status": "ok", **result, "run_id": row.id}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}

    def run_morning_preopen(
        self, asof: date | None = None, *, run_id: int | None = None
    ) -> dict[str, Any]:
        """调度：晨会开盘前篇。"""
        from desk_morning_brief import MorningBriefService

        row = self._begin("run_morning_preopen", run_id)
        try:
            brief = MorningBriefService(self.db).run_preopen(asof)
            self.store.finish(row, status="ok", message=brief.stage)
            return {"status": "ok", "brief": brief.model_dump(), "run_id": row.id}
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}

    def run_morning_post_auction(
        self, asof: date | None = None, *, run_id: int | None = None
    ) -> dict[str, Any]:
        """调度：竞价快照 + 强势选拔。"""
        from desk_market.auction_ingest import AuctionSnapshotIngestor
        from desk_morning_brief import MorningBriefService

        row = self._begin("run_morning_post_auction", run_id)
        asof = asof or date.today()
        try:
            if not CalendarService(self.db).require_trade_day(asof):
                self.store.finish(row, status="ok", message="skipped_non_trade_day")
                return {"status": "ok", "skipped": True, "run_id": row.id}
            ingest = AuctionSnapshotIngestor(self.db, self.md, asof=asof).run()
            report = MorningBriefService(self.db).run_post_auction(asof)
            self.store.finish(
                row,
                status="ok",
                symbols_done=len(report.stocks),
                message=f"written={ingest.get('written', 0)};boards={len(report.boards)}",
            )
            return {
                "status": "ok",
                "ingest": ingest,
                "report": report.model_dump(),
                "run_id": row.id,
            }
        except Exception as exc:  # noqa: BLE001
            self.store.finish(row, status="failed", error_summary=str(exc))
            return {"status": "failed", "error": str(exc), "run_id": row.id}
