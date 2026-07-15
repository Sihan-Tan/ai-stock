"""日终日线增量：近 N 日窗口 upsert，不因 daily_start 扩成全量。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import SecurityMeta
from desk_market import MarketService
from desk_market.qmt_md import QmtMarketData


class DailyBarIngestor:
    """
    全 A 在市日终增量。

    只拉 [asof-(N-1), asof]；不因 daily_start_date 扩成历史全量。
    """

    def __init__(
        self,
        db: Session,
        md: QmtMarketData,
        symbols: list[str] | None = None,
        incremental_days: int = 3,
        asof: date | None = None,
        daily_start_date: date | None = None,
    ) -> None:
        self.db = db
        self.md = md
        self.symbols = symbols
        self.incremental_days = max(1, incremental_days)
        self.asof = asof or date.today()
        self.daily_start_date = daily_start_date

    def _resolve_symbols(self) -> list[str]:
        """解析在市宇宙。"""
        if self.symbols is not None:
            return [normalize_symbol(s) for s in self.symbols]
        rows = self.db.scalars(
            select(SecurityMeta).where(SecurityMeta.is_delisted.is_(False))
        ).all()
        if rows:
            return [r.symbol for r in rows]
        return self.md.list_a_share_symbols(include_delisted=False)

    def _window(self) -> tuple[date, date]:
        """近 N 日闭区间；可被 daily_start_date 裁下界，但不会为对齐起始日扩窗。"""
        end = self.asof
        start = end - timedelta(days=self.incremental_days - 1)
        if self.daily_start_date and start < self.daily_start_date:
            start = self.daily_start_date
        return start, end

    def run(self, on_progress: Any | None = None) -> dict[str, Any]:
        """
        执行近窗增量拉取并 upsert。

        @param on_progress: 可选回调 ``(symbols_done, message)``
        @returns: symbols_done / errors
        """
        start, end = self._window()
        svc = MarketService(self.db)
        symbols_done = 0
        errors: list[str] = []
        for symbol in self._resolve_symbols():
            try:
                df = self.md.get_daily_bars(symbol, start, end)
                written = svc.upsert_daily_bars(symbol, df) if not df.empty else 0
                if written:
                    symbols_done += 1
            except Exception as exc:  # noqa: BLE001 — 单标的失败不阻断整批
                errors.append(f"{symbol}: {exc}")
            if on_progress is not None:
                on_progress(symbols_done, f"last={symbol}")
        self.db.flush()
        return {"symbols_done": symbols_done, "errors": errors}
