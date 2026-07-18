"""行情服务：入库、自选、板块成分。"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BarDaily, BarMinute, BoardMember, QuoteSnapshot, WatchlistItem
from desk_market.prices import round_price


class MarketService:
    """行情领域服务。"""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _row_has_ohlcv_and_hfq(row: pd.Series) -> bool:
        """默认 OHLCV 与 *_hfq 是否齐备（缺侧则跳过该行）。"""
        required = (
            "open",
            "high",
            "low",
            "close",
            "volume",
            "open_hfq",
            "high_hfq",
            "low_hfq",
            "close_hfq",
            "volume_hfq",
        )
        for key in required:
            if key not in row.index or pd.isna(row[key]):
                return False
        return True

    def upsert_daily_bars(self, symbol: str, df: pd.DataFrame) -> int:
        """
        Upsert 日线（默认列=前复权，另存 *_hfq）。

        仅当默认 OHLCV 与 *_hfq 齐备才写入；缺侧跳过，不计入返回值。

        @param symbol: 标的
        @param df: 含 date/open/high/low/close/volume/amount 与 *_hfq
        @returns: 写入行数
        """
        symbol = normalize_symbol(symbol)
        count = 0
        for _, row in df.iterrows():
            if not self._row_has_ohlcv_and_hfq(row):
                continue
            ts = row["date"]
            if isinstance(ts, datetime):
                ts = ts.date()
            open_ = round_price(row["open"])
            high = round_price(row["high"])
            low = round_price(row["low"])
            close = round_price(row["close"])
            volume = float(row["volume"])
            amount = float(row.get("amount", 0) or 0)
            open_hfq = round_price(row["open_hfq"])
            high_hfq = round_price(row["high_hfq"])
            low_hfq = round_price(row["low_hfq"])
            close_hfq = round_price(row["close_hfq"])
            volume_hfq = float(row["volume_hfq"])
            existing = self.db.scalar(
                select(BarDaily).where(BarDaily.symbol == symbol, BarDaily.ts == ts)
            )
            if existing:
                existing.open = open_
                existing.high = high
                existing.low = low
                existing.close = close
                existing.volume = volume
                existing.amount = amount
                existing.open_hfq = open_hfq
                existing.high_hfq = high_hfq
                existing.low_hfq = low_hfq
                existing.close_hfq = close_hfq
                existing.volume_hfq = volume_hfq
            else:
                self.db.add(
                    BarDaily(
                        symbol=symbol,
                        ts=ts,
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        amount=amount,
                        open_hfq=open_hfq,
                        high_hfq=high_hfq,
                        low_hfq=low_hfq,
                        close_hfq=close_hfq,
                        volume_hfq=volume_hfq,
                    )
                )
            count += 1
        self.db.flush()
        return count

    def load_daily_df(
        self, symbol: str, start: date, end: date, adj: str | None = None
    ) -> pd.DataFrame:
        """
        从库加载日线 DataFrame。

        @param adj: None/qfq/forward → 默认前复权列；hfq → 映射 *_hfq 到同名列
        """
        symbol = normalize_symbol(symbol)
        use_hfq = adj == "hfq"
        rows = self.db.scalars(
            select(BarDaily)
            .where(BarDaily.symbol == symbol, BarDaily.ts >= start, BarDaily.ts <= end)
            .order_by(BarDaily.ts)
        ).all()
        return pd.DataFrame(
            [
                {
                    "date": r.ts,
                    "open": float(r.open_hfq if use_hfq else r.open),
                    "high": float(r.high_hfq if use_hfq else r.high),
                    "low": float(r.low_hfq if use_hfq else r.low),
                    "close": float(r.close_hfq if use_hfq else r.close),
                    "volume": float(r.volume_hfq if use_hfq else r.volume),
                    "amount": float(r.amount),
                }
                for r in rows
            ]
        )

    def load_minute_df(
        self,
        symbol: str,
        start: date | datetime,
        end: date | datetime,
        *,
        resample: str | None = None,
    ) -> pd.DataFrame:
        """
        从库加载分钟线；可选重采样为 5min 等。

        @param symbol: 标的
        @param start: 起始日/时
        @param end: 结束日/时
        @param resample: 如 ``5min``；None 表示原始 1 分钟
        @returns: 列 date/open/high/low/close/volume/amount（date 为时间戳）
        """
        symbol = normalize_symbol(symbol)
        if isinstance(start, date) and not isinstance(start, datetime):
            start_ts = datetime.combine(start, time(9, 15))
        else:
            start_ts = start
        if isinstance(end, date) and not isinstance(end, datetime):
            end_ts = datetime.combine(end, time(15, 0))
        else:
            end_ts = end
        rows = self.db.scalars(
            select(BarMinute)
            .where(
                BarMinute.symbol == symbol,
                BarMinute.ts >= start_ts,
                BarMinute.ts <= end_ts,
            )
            .order_by(BarMinute.ts)
        ).all()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(
            [
                {
                    "date": r.ts,
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": float(r.volume),
                    "amount": float(r.amount),
                }
                for r in rows
            ]
        )
        if not resample:
            return df
        indexed = df.set_index(pd.to_datetime(df["date"]))
        indexed.index.name = "date"
        out = (
            indexed.resample(resample)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "amount": "sum",
                }
            )
            .dropna(subset=["open", "close"])
            .reset_index()
        )
        return out

    def upsert_minute_bars(self, symbol: str, df: pd.DataFrame) -> int:
        """
        Upsert 分钟线（不写复权双列）。

        @param symbol: 标的
        @param df: 含 ts/open/high/low/close/volume/amount
        @returns: 写入行数
        """
        symbol = normalize_symbol(symbol)
        if df is None or df.empty:
            return 0
        count = 0
        for _, row in df.iterrows():
            ts = row["ts"]
            if not isinstance(ts, datetime):
                ts = pd.Timestamp(ts).to_pydatetime()
            existing = self.db.scalar(
                select(BarMinute).where(BarMinute.symbol == symbol, BarMinute.ts == ts)
            )
            o = round_price(row["open"])
            h = round_price(row["high"])
            l = round_price(row["low"])
            c = round_price(row["close"])
            vol = float(row.get("volume", 0) or 0)
            amt = float(row.get("amount", 0) or 0)
            if existing:
                existing.open, existing.high, existing.low, existing.close = o, h, l, c
                existing.volume, existing.amount = vol, amt
            else:
                self.db.add(
                    BarMinute(
                        symbol=symbol,
                        ts=ts,
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=vol,
                        amount=amt,
                    )
                )
            count += 1
        self.db.flush()
        return count

    def purge_minute_before(self, cutoff: datetime) -> int:
        """
        删除严格早于 cutoff 的分钟行。

        @param cutoff: 时间切点
        @returns: 删除行数
        """
        rows = self.db.scalars(select(BarMinute).where(BarMinute.ts < cutoff)).all()
        n = len(rows)
        for r in rows:
            self.db.delete(r)
        self.db.flush()
        return n

    def list_watchlist(self, md: Any | None = None) -> list[dict[str, Any]]:
        """
        自选列表；可选合并实时快照与库内板块。

        @param md: 行情源；提供时用 ``get_snapshots`` 覆盖价量字段
        """
        from desk_market.em_boards import annotate_primary_boards

        items = self.db.scalars(select(WatchlistItem).order_by(WatchlistItem.id)).all()
        quotes = {
            q.symbol: q
            for q in self.db.scalars(select(QuoteSnapshot)).all()
        }
        symbols = [it.symbol for it in items]
        snaps: dict[str, dict[str, Any]] = {}
        if md is not None and symbols:
            try:
                snaps = md.get_snapshots(symbols) or {}
            except Exception:  # noqa: BLE001
                snaps = {}

        board_rows = []
        if symbols:
            board_rows = self.db.scalars(
                select(BoardMember).where(
                    BoardMember.symbol.in_(symbols),
                    BoardMember.effective_to.is_(None),
                )
            ).all()
        boards_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in board_rows:
            boards_by_symbol.setdefault(row.symbol, []).append(
                {
                    "board_code": row.board_code,
                    "board_name": row.board_name,
                    "board_type": row.board_type,
                }
            )
        for symbol, raw in list(boards_by_symbol.items()):
            boards_by_symbol[symbol] = annotate_primary_boards(raw)

        out = []
        for it in items:
            q = quotes.get(it.symbol)
            snap = snaps.get(it.symbol) if isinstance(snaps, dict) else None
            if not isinstance(snap, dict):
                snap = {}
            name = (
                str(snap.get("name") or "").strip()
                or it.name
                or (q.name if q else "")
            )
            last = snap.get("last")
            if last is None and q is not None:
                last = q.last
            pre_close = snap.get("pre_close")
            pct_chg = snap.get("pct_chg")
            if pct_chg is None and q is not None:
                pct_chg = q.pct_chg
            volume = snap.get("volume")
            turnover_rate = snap.get("turnover_rate")
            change = None
            if last is not None and pre_close is not None:
                try:
                    change = float(last) - float(pre_close)
                except (TypeError, ValueError):
                    change = None
            primary_boards = [
                b
                for b in boards_by_symbol.get(it.symbol, [])
                if b.get("is_primary")
            ]
            out.append(
                {
                    "symbol": it.symbol,
                    "name": name,
                    "last": last,
                    "pre_close": pre_close,
                    "pct_chg": pct_chg,
                    "change": change,
                    "volume": volume,
                    "turnover_rate": turnover_rate,
                    "boards": primary_boards,
                }
            )
        return out

    def add_watchlist(self, symbol: str, name: str = "") -> dict[str, Any]:
        """添加自选。"""
        symbol = normalize_symbol(symbol)
        existing = self.db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol))
        if existing:
            return {"symbol": existing.symbol, "name": existing.name}
        item = WatchlistItem(symbol=symbol, name=name)
        self.db.add(item)
        self.db.flush()
        return {"symbol": symbol, "name": name}

    def remove_watchlist(self, symbol: str) -> dict[str, Any]:
        """
        移除自选。

        @param symbol: 标的代码
        @returns: ``{\"symbol\": ..., \"removed\": bool}``
        """
        symbol = normalize_symbol(symbol)
        existing = self.db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol))
        if not existing:
            return {"symbol": symbol, "removed": False}
        self.db.delete(existing)
        self.db.flush()
        return {"symbol": symbol, "removed": True}

    def upsert_quote(self, symbol: str, name: str, last: float, pct_chg: float, amount: float) -> None:
        """更新快照。"""
        symbol = normalize_symbol(symbol)
        last = round_price(last)
        q = self.db.scalar(select(QuoteSnapshot).where(QuoteSnapshot.symbol == symbol))
        if q:
            q.name, q.last, q.pct_chg, q.amount = name, last, pct_chg, amount
            q.updated_at = datetime.utcnow()
        else:
            self.db.add(
                QuoteSnapshot(
                    symbol=symbol, name=name, last=last, pct_chg=pct_chg, amount=amount
                )
            )
        self.db.flush()

    def list_boards(self, board_type: str | None = None) -> list[dict[str, Any]]:
        """板块/概念列表（按最新成分聚合）。"""
        q = select(BoardMember)
        if board_type:
            q = q.where(BoardMember.board_type == board_type)
        rows = self.db.scalars(q).all()
        boards: dict[str, dict[str, Any]] = {}
        for r in rows:
            if r.board_code not in boards:
                boards[r.board_code] = {
                    "board_code": r.board_code,
                    "board_name": r.board_name,
                    "board_type": r.board_type,
                    "members": 0,
                }
            boards[r.board_code]["members"] += 1
        return list(boards.values())
