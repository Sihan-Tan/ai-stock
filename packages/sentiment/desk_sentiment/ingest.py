"""情绪日终落库。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_common.beijing_time import beijing_today
from desk_db.models import LimitUpStat, LimitUpStock, SecurityMeta
from desk_sentiment.aggregator import aggregate_limit_rows
from desk_sentiment.qmt_client import QmtSentimentClient


class SentimentDailyIngestor:
    """按 asof 快照替换写入 limit_up_*。"""

    def __init__(
        self,
        db: Session,
        client: QmtSentimentClient,
        asof: date | None = None,
        symbols: list[str] | None = None,
    ) -> None:
        self.db = db
        self.client = client
        self.asof = asof or beijing_today()
        self.symbols = symbols

    def _universe(self) -> list[str]:
        if self.symbols is not None:
            return [normalize_symbol(s) for s in self.symbols]
        rows = self.db.scalars(
            select(SecurityMeta).where(SecurityMeta.is_delisted.is_(False))
        ).all()
        return [r.symbol for r in rows]

    def run(self) -> dict[str, Any]:
        """
        拉取、聚合、快照替换。

        @returns: symbols_done / cover / errors
        """
        universe = self._universe()
        if not universe:
            raise RuntimeError("empty_universe")
        try:
            raw = self.client.fetch_limit_performance(universe, self.asof)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)) from exc

        # 源为空时不覆盖已有快照，避免写入全 0 挡住「最近一日」回退
        if not raw:
            return {
                "symbols_done": 0,
                "cover": 0,
                "universe": len(universe),
                "errors": ["empty_source"],
                "skipped_write": True,
            }

        agg = aggregate_limit_rows(raw)
        asof = self.asof
        self.db.execute(delete(LimitUpStock).where(LimitUpStock.asof == asof))
        existing = self.db.scalar(select(LimitUpStat).where(LimitUpStat.asof == asof))
        st = agg["stat"]
        if existing:
            existing.limit_up_count = st["limit_up_count"]
            existing.limit_down_count = st["limit_down_count"]
            existing.max_board = st["max_board"]
            existing.promote_rate = st["promote_rate"]
            existing.break_rate = st["break_rate"]
        else:
            self.db.add(
                LimitUpStat(
                    asof=asof,
                    limit_up_count=st["limit_up_count"],
                    limit_down_count=st["limit_down_count"],
                    max_board=st["max_board"],
                    promote_rate=st["promote_rate"],
                    break_rate=st["break_rate"],
                )
            )
        for s in agg["stocks"]:
            self.db.add(
                LimitUpStock(
                    asof=asof,
                    symbol=normalize_symbol(s["symbol"]),
                    name=s.get("name") or "",
                    board_height=int(s["board_height"]),
                    seal_amount=float(s["seal_amount"]),
                    concept=s.get("concept") or "",
                    status=s["status"],
                )
            )
        self.db.flush()
        return {
            "symbols_done": len(agg["stocks"]),
            "cover": len(raw),
            "universe": len(universe),
            "errors": [],
        }
