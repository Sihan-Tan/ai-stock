"""历史日线缺口回填：≥ daily_start_date，优先 QMT，空/失败再 AkShare。"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BarDaily, SecurityMeta
from desk_market import MarketService
from desk_market.qmt_md import QmtMarketData


class DailyBarClient(Protocol):
    """日线拉取协议（AkShare Fake / Client）。"""

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """拉取日线。"""
        ...


class HistoryBackfill:
    """
    历史缺口回填。

    `forced_gap` 仅供测试注入缺口窗口；生产路径按 MAX(ts) 推断。
    """

    def __init__(
        self,
        db: Session,
        md: QmtMarketData,
        akshare: DailyBarClient,
        daily_start_date: date,
        symbols: list[str] | None = None,
        asof: date | None = None,
        forced_gap: tuple[date, date] | None = None,
    ) -> None:
        self.db = db
        self.md = md
        self.akshare = akshare
        self.daily_start_date = daily_start_date
        self.symbols = symbols
        self.asof = asof or date.today()
        self.forced_gap = forced_gap

    def _resolve_symbols(self) -> list[str]:
        """在市宇宙。"""
        if self.symbols is not None:
            return [normalize_symbol(s) for s in self.symbols]
        rows = self.db.scalars(
            select(SecurityMeta).where(SecurityMeta.is_delisted.is_(False))
        ).all()
        if rows:
            return [r.symbol for r in rows]
        return self.md.list_a_share_symbols(include_delisted=False)

    def _gap_for(self, symbol: str) -> tuple[date, date] | None:
        """计算裁剪后的缺口窗口。"""
        if self.forced_gap is not None:
            start, end = self.forced_gap
        else:
            max_ts = self.db.scalar(
                select(func.max(BarDaily.ts)).where(BarDaily.symbol == symbol)
            )
            if max_ts is None:
                start = self.daily_start_date
            else:
                start = max_ts if isinstance(max_ts, date) else max_ts.date()
                # 从已有最后一日之后继续（简化：同一日再拉也能幂等）
                start = start
            end = self.asof
        if start < self.daily_start_date:
            start = self.daily_start_date
        if end < start:
            return None
        return start, end

    def run(self, on_progress: Any | None = None) -> dict[str, Any]:
        """
        执行回填。

        @param on_progress: 可选回调 ``(symbols_done, message)``
        @returns: symbols_done / errors
        """
        svc = MarketService(self.db)
        symbols_done = 0
        errors: list[str] = []
        for symbol in self._resolve_symbols():
            gap = self._gap_for(symbol)
            if gap is None:
                continue
            start, end = gap
            try:
                df = self.md.get_daily_bars(symbol, start, end)
                if df is None or df.empty:
                    df = self.akshare.get_daily_bars(symbol, start, end)
                written = svc.upsert_daily_bars(symbol, df) if df is not None and not df.empty else 0
                if written:
                    symbols_done += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}: {exc}")
            if on_progress is not None:
                on_progress(symbols_done, f"last={symbol}")
        self.db.flush()
        return {"symbols_done": symbols_done, "errors": errors}
