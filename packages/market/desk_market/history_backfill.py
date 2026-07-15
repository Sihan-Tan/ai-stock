"""历史日线缺口回填：≥ daily_start_date，优先 QMT，空/失败再 AkShare。

对齐 ``example/1``、``example/8``：
- 无数据或最早日晚于 ``daily_start_date`` → 从起始日全量/补齐（非仅从 MAX 向前）
- QMT：``download_history_data`` + ``get_market_data_ex(front/back)``
- 同起点标的按批批量拉取，提升吞吐
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BarDaily, SecurityMeta
from desk_market import MarketService
from desk_market.akshare_daily import akshare_supports_symbol
from desk_market.qmt_md import QmtMarketData

# 与 example 类似的批大小：同起点一批 download + 批量 get_market_data_ex
_BATCH_SIZE = 50


class DailyBarClient(Protocol):
    """日线拉取协议（AkShare Fake / Client）。"""

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """拉取日线。"""
        ...


class HistoryBackfill:
    """
    历史缺口回填。

    `forced_gap` 仅供测试注入缺口窗口；生产路径按 min/max(ts) 推断。
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
        batch_size: int = _BATCH_SIZE,
    ) -> None:
        self.db = db
        self.md = md
        self.akshare = akshare
        self.daily_start_date = daily_start_date
        self.symbols = symbols
        self.asof = asof or date.today()
        self.forced_gap = forced_gap
        self.batch_size = max(1, batch_size)

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
        """
        计算裁剪后的缺口窗口。

        - 无数据：``[daily_start_date, asof]``
        - 已有数据但 ``min(ts) > daily_start_date``：视为历史未齐，从起始日重拉（upsert 幂等）
        - 否则：仅从 ``max(ts)`` 向 ``asof`` 增量（对齐 example 增量逻辑）
        """
        if self.forced_gap is not None:
            start, end = self.forced_gap
        else:
            min_ts = self.db.scalar(
                select(func.min(BarDaily.ts)).where(BarDaily.symbol == symbol)
            )
            max_ts = self.db.scalar(
                select(func.max(BarDaily.ts)).where(BarDaily.symbol == symbol)
            )
            end = self.asof
            if max_ts is None:
                start = self.daily_start_date
            else:
                max_d = max_ts if isinstance(max_ts, date) else max_ts.date()
                min_d = (
                    min_ts
                    if isinstance(min_ts, date)
                    else (min_ts.date() if min_ts is not None else max_d)
                )
                if min_d > self.daily_start_date:
                    # 历史不完整（例如只有近几日）：从配置起始日重拉
                    start = self.daily_start_date
                else:
                    start = max_d
        if start < self.daily_start_date:
            start = self.daily_start_date
        if end < start:
            return None
        return start, end

    def _fetch_one(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """单标的：QMT →（沪深）AkShare。"""
        df = self.md.get_daily_bars(symbol, start, end)
        if df is not None and not df.empty:
            return df
        if akshare_supports_symbol(symbol):
            try:
                return self.akshare.get_daily_bars(symbol, start, end)
            except Exception:  # noqa: BLE001
                return pd.DataFrame()
        return pd.DataFrame()

    def _fetch_batch(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """
        同起点批量拉取（有 ``get_daily_bars_batch`` 时用；否则逐只）。

        @returns: symbol → DataFrame
        """
        batch_fn = getattr(self.md, "get_daily_bars_batch", None)
        out: dict[str, pd.DataFrame] = {}
        if callable(batch_fn):
            try:
                out = batch_fn(symbols, start, end) or {}
            except Exception:  # noqa: BLE001
                out = {}
        for sym in symbols:
            df = out.get(sym)
            if df is None or df.empty:
                out[sym] = self._fetch_one(sym, start, end)
        return out

    def run(self, on_progress: Any | None = None) -> dict[str, Any]:
        """
        执行回填。

        @param on_progress: 可选回调 ``(symbols_done, message)``
        @returns: symbols_done / errors / refill_incomplete
        """
        svc = MarketService(self.db)
        symbols_done = 0
        errors: list[str] = []
        refill_incomplete = 0

        # 按起点分组，便于批量 download（对齐 example）
        groups: dict[date, list[str]] = {}
        for symbol in self._resolve_symbols():
            gap = self._gap_for(symbol)
            if gap is None:
                continue
            start, end = gap
            if start == self.daily_start_date:
                # 统计「从起始日重拉」的数量
                min_ts = self.db.scalar(
                    select(func.min(BarDaily.ts)).where(BarDaily.symbol == symbol)
                )
                if min_ts is not None:
                    min_d = min_ts if isinstance(min_ts, date) else min_ts.date()
                    if min_d > self.daily_start_date:
                        refill_incomplete += 1
            groups.setdefault(start, []).append(symbol)

        for start, syms in groups.items():
            end = self.asof
            for i in range(0, len(syms), self.batch_size):
                chunk = syms[i : i + self.batch_size]
                try:
                    frames = self._fetch_batch(chunk, start, end)
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)
                    if len(msg) > 160:
                        msg = msg[:157] + "..."
                    for symbol in chunk:
                        errors.append(f"{symbol}: {msg}")
                    if on_progress is not None:
                        on_progress(symbols_done, f"batch_err@{start}")
                    continue

                for symbol in chunk:
                    try:
                        df = frames.get(symbol)
                        written = (
                            svc.upsert_daily_bars(symbol, df)
                            if df is not None and not df.empty
                            else 0
                        )
                        if written:
                            symbols_done += 1
                    except Exception as exc:  # noqa: BLE001
                        msg = str(exc)
                        if len(msg) > 160:
                            msg = msg[:157] + "..."
                        errors.append(f"{symbol}: {msg}")
                    if on_progress is not None:
                        on_progress(symbols_done, f"last={symbol}")
                self.db.flush()

        self.db.flush()
        return {
            "symbols_done": symbols_done,
            "errors": errors,
            "refill_incomplete": refill_incomplete,
        }
