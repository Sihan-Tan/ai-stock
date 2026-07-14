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

    def upsert_daily_bars(self, symbol: str, df: pd.DataFrame) -> int:
        """
        Upsert 日线。

        @param symbol: 标的
        @param df: 含 date/open/high/low/close/volume/amount
        @returns: 写入行数
        """
        symbol = normalize_symbol(symbol)
        count = 0
        for _, row in df.iterrows():
            ts = row["date"]
            if isinstance(ts, datetime):
                ts = ts.date()
            existing = self.db.scalar(
                select(BarDaily).where(BarDaily.symbol == symbol, BarDaily.ts == ts)
            )
            if existing:
                existing.open = float(row["open"])
                existing.high = float(row["high"])
                existing.low = float(row["low"])
                existing.close = float(row["close"])
                existing.volume = float(row.get("volume", 0) or 0)
                existing.amount = float(row.get("amount", 0) or 0)
            else:
                self.db.add(
                    BarDaily(
                        symbol=symbol,
                        ts=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0) or 0),
                        amount=float(row.get("amount", 0) or 0),
                    )
                )
            count += 1
        self.db.flush()
        return count

    def load_daily_df(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """从库加载日线 DataFrame。"""
        symbol = normalize_symbol(symbol)
        rows = self.db.scalars(
            select(BarDaily)
            .where(BarDaily.symbol == symbol, BarDaily.ts >= start, BarDaily.ts <= end)
            .order_by(BarDaily.ts)
        ).all()
        return pd.DataFrame(
            [
                {
                    "date": r.ts,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
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
                    rows.append(
                        {
                            "date": d,
                            "open": price * 0.99,
                            "high": price * 1.01,
                            "low": price * 0.98,
                            "close": price,
                            "volume": 1e6,
                            "amount": price * 1e6,
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
