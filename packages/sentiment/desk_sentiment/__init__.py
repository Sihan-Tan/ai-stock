"""打板情绪。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk_common.beijing_time import beijing_today
from desk_db.models import LimitUpStat, LimitUpStock
from desk_sentiment.aggregator import aggregate_limit_rows
from desk_sentiment.akshare_client import AkshareSentimentClient, FallbackSentimentClient
from desk_sentiment.ingest import SentimentDailyIngestor
from desk_sentiment.qmt_client import MockQmtSentimentClient, QmtSentimentClient, XtdataSentimentClient

__all__ = [
    "SentimentService",
    "aggregate_limit_rows",
    "SentimentDailyIngestor",
    "MockQmtSentimentClient",
    "QmtSentimentClient",
    "XtdataSentimentClient",
    "AkshareSentimentClient",
    "FallbackSentimentClient",
]


class SentimentService:
    """涨停情绪服务。"""

    def __init__(self, db: Session):
        self.db = db

    def _latest_asof(self) -> date | None:
        """库中最新有情绪统计的交易日。"""
        return self.db.scalar(select(func.max(LimitUpStat.asof)))

    def resolve_asof(self, asof: date | None = None) -> date:
        """
        解析查询日：显式 asof 优先；否则北京今日（需有有效涨停数据）；
        否则回退到最近 limit_up_count>0 的交易日。

        @param asof: 指定交易日；None 表示自动
        """
        if asof is not None:
            return asof
        today = beijing_today()
        today_stat = self.db.scalar(select(LimitUpStat).where(LimitUpStat.asof == today))
        if today_stat is not None and int(today_stat.limit_up_count or 0) > 0:
            return today
        latest_positive = self.db.scalar(
            select(func.max(LimitUpStat.asof)).where(LimitUpStat.limit_up_count > 0)
        )
        if latest_positive is not None:
            return latest_positive
        latest = self._latest_asof()
        return latest or today

    def snapshot(self, asof: date | None = None) -> dict[str, Any]:
        """情绪快照（默认展示今日；无数据则展示最近一日）。"""
        resolved = self.resolve_asof(asof)
        stat = self.db.scalar(select(LimitUpStat).where(LimitUpStat.asof == resolved))
        stocks = self.db.scalars(
            select(LimitUpStock)
            .where(LimitUpStock.asof == resolved)
            .order_by(LimitUpStock.board_height.desc())
        ).all()
        return {
            "asof": resolved.isoformat(),
            "limit_up_count": stat.limit_up_count if stat else 0,
            "limit_down_count": stat.limit_down_count if stat else 0,
            "max_board": stat.max_board if stat else 0,
            "promote_rate": stat.promote_rate if stat else 0.0,
            "break_rate": stat.break_rate if stat else 0.0,
            "ladder": [
                {
                    "symbol": s.symbol,
                    "name": s.name,
                    "board_height": s.board_height,
                    "seal_amount": s.seal_amount,
                    "concept": s.concept,
                    "status": s.status,
                }
                for s in stocks
            ],
        }
