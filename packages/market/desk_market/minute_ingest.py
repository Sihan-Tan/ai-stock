"""分钟线：自选∪指数宇宙 + 近 3 交易日滚动 purge。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import SecurityMeta, TradeCalendar, WatchlistItem
from desk_market import MarketService
from desk_market.qmt_md import QmtMarketData


def compute_minute_purge_cutoff(db: Session, asof: date, keep_trade_days: int = 3) -> datetime:
    """
    计算分钟清理切点：保留最近 keep_trade_days 个交易日，删除更早数据。

    切点 = 第 (keep_trade_days+1) 个交易日（含 asof 往前）的 09:30。

    @param db: 会话
    @param asof: 当前交易日
    @param keep_trade_days: 保留交易日数，默认 3
    @returns: naive datetime 切点
    """
    open_days = db.scalars(
        select(TradeCalendar.cal_date)
        .where(TradeCalendar.is_open.is_(True), TradeCalendar.cal_date <= asof)
        .order_by(TradeCalendar.cal_date.desc())
    ).all()
    # 保留 asof + 最近 keep_trade_days-? :
    # open_days[0]=asof … open_days[keep_trade_days-1] 为第 keep 个既往日的下一档
    # 切点 = 仍保留的最旧交易日开盘 09:30（严格早于者删除）
    idx = keep_trade_days  # asof + (keep_trade_days-1) 既往 → 最旧保留 index = keep_trade_days-?
    # 保留天：asof 与往前 keep_trade_days 个（含往前 3 个 + asof 共 4 天）→ 最旧保留 index = keep_trade_days
    # open_days: [8,5,4,3,2] keep 8,5,4,3 → index 3 = Jan3；删 < Jan3 09:30
    idx = keep_trade_days
    if len(open_days) <= idx:
        boundary = open_days[-1] if open_days else asof - timedelta(days=30)
    else:
        boundary = open_days[idx]
    return datetime.combine(boundary, time(9, 30, 0))


class MinuteBarIngestor:
    """自选 ∪ 指数分钟 upsert，末尾按 3 交易日 purge。"""

    def __init__(
        self,
        db: Session,
        md: QmtMarketData,
        index_symbols: list[str] | None = None,
        asof: date | None = None,
        purge: bool = True,
    ) -> None:
        self.db = db
        self.md = md
        self.index_symbols = [normalize_symbol(s) for s in (index_symbols or [])]
        self.asof = asof or date.today()
        self.purge = purge

    def _universe(self) -> list[str]:
        """watchlist ∪ indices，去掉退市。"""
        delisted = {
            r.symbol
            for r in self.db.scalars(
                select(SecurityMeta).where(SecurityMeta.is_delisted.is_(True))
            ).all()
        }
        watch = [
            normalize_symbol(r.symbol)
            for r in self.db.scalars(select(WatchlistItem)).all()
        ]
        merged = sorted(set(watch) | set(self.index_symbols))
        return [s for s in merged if s not in delisted]

    def run(self) -> dict[str, Any]:
        """拉取并入库；可选 purge。"""
        svc = MarketService(self.db)
        start = f"{self.asof.isoformat()} 09:30:00"
        end = f"{self.asof.isoformat()} 15:00:00"
        done = 0
        errors: list[str] = []
        for symbol in self._universe():
            try:
                df = self.md.get_minute_bars(symbol, start, end)
                if df is not None and not df.empty:
                    done += svc.upsert_minute_bars(symbol, df)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}: {exc}")
        purged = 0
        if self.purge:
            cutoff = compute_minute_purge_cutoff(self.db, self.asof)
            purged = svc.purge_minute_before(cutoff)
        self.db.flush()
        return {"bars_written": done, "purged": purged, "errors": errors}
