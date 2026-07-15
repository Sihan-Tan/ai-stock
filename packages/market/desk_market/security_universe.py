"""标的宇宙同步：退市过滤与 SecurityMeta 维护。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import SecurityMeta
from desk_market.qmt_md import QmtMarketData


class SecurityListSync:
    """从行情源同步标的列表，标记退市并返回在市宇宙。"""

    def __init__(self, db: Session, md: QmtMarketData) -> None:
        self.db = db
        self.md = md

    def run(self) -> list[str]:
        """
        同步标的元数据并返回在市符号列表。

        @returns: status 为 listed 的规范化 symbol 列表
        """
        universe: list[str] = []
        for info in self.md.list_instruments():
            sym = normalize_symbol(info.symbol)
            is_delisted = info.status == "delisted"
            existing = self.db.scalar(
                select(SecurityMeta).where(SecurityMeta.symbol == sym)
            )
            if existing:
                existing.name = info.name
                existing.is_delisted = is_delisted
                existing.status = info.status
                existing.updated_at = datetime.utcnow()
            else:
                self.db.add(
                    SecurityMeta(
                        symbol=sym,
                        name=info.name,
                        is_delisted=is_delisted,
                        status=info.status,
                    )
                )
            if not is_delisted:
                universe.append(sym)
        self.db.flush()
        return universe
