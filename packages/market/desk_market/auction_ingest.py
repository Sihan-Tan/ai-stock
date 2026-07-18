"""集合竞价快照：自选宇宙 + QMT 快照落库，供晨会竞价选拔。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import AuctionSnapshot, BoardMember, SecurityMeta, WatchlistItem
from desk_market.em_boards import annotate_primary_boards
from desk_market.qmt_md import QmtMarketData


class AuctionSnapshotIngestor:
    """
    拉取竞价阶段价量并写入 ``auction_snapshots``。

    宇宙默认：自选；自选为空时回退到未退市 SecurityMeta（上限 batch）。
    """

    def __init__(
        self,
        db: Session,
        md: QmtMarketData,
        asof: date | None = None,
        *,
        exclude_st: bool = True,
        max_universe: int = 400,
    ) -> None:
        self.db = db
        self.md = md
        self.asof = asof or date.today()
        self.exclude_st = exclude_st
        self.max_universe = max_universe

    def _universe(self) -> list[str]:
        """自选优先，否则未退市证券列表截断。"""
        watch = [
            normalize_symbol(r.symbol)
            for r in self.db.scalars(select(WatchlistItem)).all()
        ]
        if watch:
            return sorted(set(watch))[: self.max_universe]
        listed = self.db.scalars(
            select(SecurityMeta.symbol).where(SecurityMeta.is_delisted.is_(False))
        ).all()
        return sorted({normalize_symbol(s) for s in listed})[: self.max_universe]

    def _primary_board(self, symbol: str) -> tuple[str, str]:
        """
        取主行业板块；无则空串。

        @param symbol: 标的
        @returns: (board_code, board_name)
        """
        rows = self.db.scalars(
            select(BoardMember).where(
                BoardMember.symbol == symbol,
                BoardMember.effective_to.is_(None),
            )
        ).all()
        if not rows:
            return "", ""
        annotated = annotate_primary_boards(
            [
                {
                    "board_code": r.board_code,
                    "board_name": r.board_name,
                    "board_type": r.board_type,
                }
                for r in rows
            ]
        )
        for item in annotated:
            if item.get("is_primary") and item.get("board_type") == "sector":
                return str(item.get("board_code") or ""), str(item.get("board_name") or "")
        for item in annotated:
            if item.get("is_primary"):
                return str(item.get("board_code") or ""), str(item.get("board_name") or "")
        return "", ""

    def run(self) -> dict[str, Any]:
        """
        拉取快照并按 asof+symbol upsert。

        @returns: written / skipped / errors 统计
        """
        symbols = self._universe()
        if not symbols:
            return {"written": 0, "skipped": 0, "errors": ["empty_universe"]}

        try:
            snaps = self.md.get_snapshots(symbols) or {}
        except Exception as exc:  # noqa: BLE001
            return {"written": 0, "skipped": 0, "errors": [str(exc)]}

        existing = {
            r.symbol: r
            for r in self.db.scalars(
                select(AuctionSnapshot).where(AuctionSnapshot.asof == self.asof)
            ).all()
        }

        written = 0
        skipped = 0
        errors: list[str] = []
        for sym in symbols:
            snap = snaps.get(sym)
            if not isinstance(snap, dict):
                skipped += 1
                continue
            name = str(snap.get("name") or "").strip()
            if self.exclude_st and "ST" in name.upper():
                skipped += 1
                continue
            last = snap.get("last")
            pre_close = snap.get("pre_close")
            try:
                last_f = float(last) if last is not None else None
                pre_f = float(pre_close) if pre_close is not None else None
            except (TypeError, ValueError):
                skipped += 1
                continue
            if last_f is None or pre_f is None or pre_f <= 0:
                skipped += 1
                continue
            auction_pct = (last_f - pre_f) / pre_f
            try:
                amount = float(snap.get("amount") or 0.0)
            except (TypeError, ValueError):
                amount = 0.0
            board_code, board_name = self._primary_board(sym)
            row = existing.get(sym)
            if row is None:
                row = AuctionSnapshot(asof=self.asof, symbol=sym)
                self.db.add(row)
                existing[sym] = row
            row.name = name
            row.auction_pct = auction_pct
            row.auction_amount = amount
            row.board_code = board_code
            row.board_name = board_name
            written += 1

        self.db.flush()
        return {
            "written": written,
            "skipped": skipped,
            "universe": len(symbols),
            "errors": errors,
        }
