"""行情服务：入库、自选、板块成分。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BarDaily, BoardMember, QuoteSnapshot, WatchlistItem


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
            open_ = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row["volume"])
            amount = float(row.get("amount", 0) or 0)
            open_hfq = float(row["open_hfq"])
            high_hfq = float(row["high_hfq"])
            low_hfq = float(row["low_hfq"])
            close_hfq = float(row["close_hfq"])
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
                    "open": r.open_hfq if use_hfq else r.open,
                    "high": r.high_hfq if use_hfq else r.high,
                    "low": r.low_hfq if use_hfq else r.low,
                    "close": r.close_hfq if use_hfq else r.close,
                    "volume": r.volume_hfq if use_hfq else r.volume,
                    "amount": r.amount,
                }
                for r in rows
            ]
        )

    def list_watchlist(self) -> list[dict[str, Any]]:
        """自选列表。"""
        items = self.db.scalars(select(WatchlistItem).order_by(WatchlistItem.id)).all()
        quotes = {
            q.symbol: q
            for q in self.db.scalars(select(QuoteSnapshot)).all()
        }
        out = []
        for it in items:
            q = quotes.get(it.symbol)
            out.append(
                {
                    "symbol": it.symbol,
                    "name": it.name or (q.name if q else ""),
                    "last": q.last if q else None,
                    "pct_chg": q.pct_chg if q else None,
                    "amount": q.amount if q else None,
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

    def upsert_quote(self, symbol: str, name: str, last: float, pct_chg: float, amount: float) -> None:
        """更新快照。"""
        symbol = normalize_symbol(symbol)
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

    def seed_demo_data(self) -> None:
        """种子演示数据（无外网也可跑）。"""
        if not self.db.scalar(select(WatchlistItem).limit(1)):
            for sym, name in [
                ("600519.SH", "贵州茅台"),
                ("300750.SZ", "宁德时代"),
                ("510300.SH", "沪深300ETF"),
            ]:
                self.add_watchlist(sym, name)
                self.upsert_quote(sym, name, 100.0, 0.5, 1e8)

        if not self.db.scalar(select(BarDaily).limit(1)):
            today = date.today()
            for sym in ["600519.SH", "300750.SZ", "510300.SH"]:
                rows = []
                price = 100.0
                for i in range(120, 0, -1):
                    d = today - timedelta(days=i)
                    if d.weekday() >= 5:
                        continue
                    price *= 1 + ((hash(f"{sym}{d}") % 21) - 10) / 1000.0
                    o, h, l, c, v = price * 0.99, price * 1.01, price * 0.98, price, 1e6
                    rows.append(
                        {
                            "date": d,
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v,
                            "amount": price * 1e6,
                            "open_hfq": o,
                            "high_hfq": h,
                            "low_hfq": l,
                            "close_hfq": c,
                            "volume_hfq": v,
                        }
                    )
                self.upsert_daily_bars(sym, pd.DataFrame(rows))

        if not self.db.scalar(select(BoardMember).limit(1)):
            self.db.add_all(
                [
                    BoardMember(
                        board_code="BK001",
                        board_name="半导体",
                        board_type="sector",
                        symbol="300750.SZ",
                        effective_from=date(2020, 1, 1),
                    ),
                    BoardMember(
                        board_code="BK002",
                        board_name="白酒",
                        board_type="concept",
                        symbol="600519.SH",
                        effective_from=date(2020, 1, 1),
                    ),
                ]
            )
            self.db.flush()
