"""晨会：开盘前 + 竞价后强势选拔。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_alert import FeishuWebhookChannel
from desk_calendar import CalendarService
from desk_common.contracts import MorningBrief, StrongPickReport
from desk_db.models import AuctionSnapshot, MorningBriefRow, MorningStrongPick
from desk_lhb import LhbService
from desk_sentiment import SentimentService


class MorningBriefService:
    """晨会服务。"""

    def __init__(self, db: Session):
        self.db = db
        self.calendar = CalendarService(db)
        self.sentiment = SentimentService(db)
        self.lhb = LhbService(db)
        self.alert = FeishuWebhookChannel(db)

    def run_preopen(self, asof: date | None = None) -> MorningBrief:
        """开盘前篇。"""
        asof = asof or date.today()
        if not self.calendar.is_trade_day(asof):
            content = f"{asof} 非交易日，跳过晨会开盘前篇。"
            return self._store(asof, "preopen", content, {})
        sent = self.sentiment.snapshot(asof)
        lhb = self.lhb.by_date(asof)
        extras = {"sentiment": sent, "lhb_count": len(lhb)}
        content = (
            f"【开盘前】{asof}\n"
            f"情绪：涨停 {sent['limit_up_count']} / 最高连板 {sent['max_board']} / 晋级率 {sent['promote_rate']:.0%}\n"
            f"龙虎榜上榜 {len(lhb)} 只\n"
            f"下一交易日：{self.calendar.next_trade_day(asof)}"
        )
        brief = self._store(asof, "preopen", content, extras)
        self.alert.send("晨会·开盘前", content, category="morning", dedupe_key=f"preopen:{asof}")
        return brief

    def run_post_auction(self, asof: date | None = None) -> StrongPickReport:
        """竞价结束后强势板块/个股。"""
        asof = asof or date.today()
        if not self.calendar.is_trade_day(asof):
            return StrongPickReport(asof=asof, boards=[], stocks=[])
        snaps = self.db.scalars(select(AuctionSnapshot).where(AuctionSnapshot.asof == asof)).all()
        if not snaps:
            self._seed_auction(asof)
            snaps = self.db.scalars(select(AuctionSnapshot).where(AuctionSnapshot.asof == asof)).all()

        # 个股打分：竞价涨幅*0.5 + 竞价额分位*0.5
        amounts = sorted(s.auction_amount for s in snaps)
        stocks = []
        for s in snaps:
            amt_score = amounts.index(s.auction_amount) / max(len(amounts) - 1, 1)
            score = s.auction_pct * 50 + amt_score * 50
            stocks.append(
                {
                    "symbol": s.symbol,
                    "name": s.name,
                    "auction_pct": s.auction_pct,
                    "auction_amount": s.auction_amount,
                    "board": s.board_name,
                    "score": round(score, 2),
                }
            )
        stocks.sort(key=lambda x: x["score"], reverse=True)
        stocks = stocks[:8]

        board_map: dict[str, list[float]] = {}
        for s in snaps:
            board_map.setdefault(s.board_name or "其它", []).append(s.auction_pct)
        boards = [
            {
                "board": b,
                "avg_pct": round(sum(v) / len(v), 4),
                "count": len(v),
                "score": round(sum(v) / len(v) * 100 + len(v), 2),
            }
            for b, v in board_map.items()
        ]
        boards.sort(key=lambda x: x["score"], reverse=True)
        boards = boards[:5]

        # 清理并写入 picks
        old = self.db.scalars(select(MorningStrongPick).where(MorningStrongPick.asof == asof)).all()
        for o in old:
            self.db.delete(o)
        for b in boards:
            self.db.add(
                MorningStrongPick(
                    asof=asof,
                    pick_type="board",
                    code=b["board"],
                    name=b["board"],
                    score=b["score"],
                    meta_json=json.dumps(b, ensure_ascii=False),
                )
            )
        for s in stocks:
            self.db.add(
                MorningStrongPick(
                    asof=asof,
                    pick_type="stock",
                    code=s["symbol"],
                    name=s["name"],
                    score=s["score"],
                    meta_json=json.dumps(s, ensure_ascii=False),
                )
            )
        stock_bits = [
            f"{s['symbol']}({s['auction_pct']:.1%})" for s in stocks[:4]
        ]
        content = (
            f"【竞价强势】{asof}\n"
            f"板块：{' / '.join(b['board'] for b in boards)}\n"
            f"个股：{' · '.join(stock_bits)}"
        )
        self._store(asof, "post_auction", content, {"boards": boards, "stocks": stocks})
        self.alert.send("晨会·竞价强势", content, category="morning", dedupe_key=f"auction:{asof}")
        self.db.flush()
        return StrongPickReport(asof=asof, boards=boards, stocks=stocks)

    def _store(self, asof: date, stage: str, content: str, extras: dict[str, Any]) -> MorningBrief:
        self.db.add(
            MorningBriefRow(
                asof=asof,
                stage=stage,
                content=content,
                extras_json=json.dumps(extras, ensure_ascii=False),
            )
        )
        self.db.flush()
        return MorningBrief(asof=asof, stage=stage, content=content, extras=extras)  # type: ignore[arg-type]

    def _seed_auction(self, asof: date) -> None:
        samples = [
            ("688001.SH", "示例半导体", 0.098, 1.2e8, "半导体"),
            ("300001.SZ", "示例AI", 0.072, 0.9e8, "人工智能"),
            ("002001.SZ", "示例机器人", 0.056, 2.4e8, "机器人"),
            ("601001.SH", "示例券商", 0.031, 3.1e8, "券商"),
            ("000002.SZ", "示例消费", 0.012, 0.5e8, "消费电子"),
        ]
        for sym, name, pct, amt, board in samples:
            self.db.add(
                AuctionSnapshot(
                    asof=asof,
                    symbol=sym,
                    name=name,
                    auction_pct=pct,
                    auction_amount=amt,
                    board_code=board,
                    board_name=board,
                )
            )
        self.db.flush()
