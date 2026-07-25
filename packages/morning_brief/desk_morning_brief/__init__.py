"""晨会 / 早盘选股：开盘前 + 竞价后强势选拔。"""

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
    """早盘选股服务（开盘前摘要 + 竞价强势）。"""

    def __init__(self, db: Session):
        self.db = db
        self.calendar = CalendarService(db)
        self.sentiment = SentimentService(db)
        self.lhb = LhbService(db)
        self.alert = FeishuWebhookChannel(db)

    def resolve_asof(self, asof: date | None = None) -> tuple[date, str]:
        """
        解析业务日：非交易日回退到上一交易日。

        @param asof: 请求日，默认今天
        @returns: (有效交易日, 文案前缀；交易日则为空串)
        """
        requested = asof or date.today()
        if self.calendar.is_trade_day(requested):
            return requested, ""
        prev = self.calendar.previous_trade_day(requested)
        note = f"{requested} 非交易日，已按上一交易日 {prev} 筛选。\n"
        return prev, note

    def run_preopen(self, asof: date | None = None) -> MorningBrief:
        """开盘前篇；休息日按上一交易日数据。"""
        requested = asof or date.today()
        asof, day_note = self.resolve_asof(requested)
        sent = self.sentiment.snapshot(asof)
        lhb = self.lhb.by_date(asof)
        extras: dict[str, Any] = {
            "sentiment": sent,
            "lhb_count": len(lhb),
        }
        if day_note:
            extras["day_note"] = day_note.strip()
            extras["requested_asof"] = requested.isoformat()
        content = (
            f"【开盘前】{asof}\n"
            f"{day_note}"
            f"情绪：涨停 {sent['limit_up_count']} / 最高连板 {sent['max_board']} / 晋级率 {sent['promote_rate']:.0%}\n"
            f"龙虎榜上榜 {len(lhb)} 只\n"
            f"下一交易日：{self.calendar.next_trade_day(asof)}"
        )
        brief = self._store(asof, "preopen", content, extras)
        self.alert.send("早盘·开盘前", content, category="morning", dedupe_key=f"preopen:{asof}")
        return brief

    def run_post_auction(self, asof: date | None = None) -> StrongPickReport:
        """竞价结束后强势板块/个股；休息日按上一交易日快照。"""
        requested = asof or date.today()
        asof, day_note = self.resolve_asof(requested)
        snaps = self.db.scalars(select(AuctionSnapshot).where(AuctionSnapshot.asof == asof)).all()
        if not snaps:
            content = (
                f"【竞价强势】{asof}\n"
                f"{day_note}"
                "暂无竞价快照，无法选拔。"
            )
            extras: dict[str, Any] = {"boards": [], "stocks": []}
            if day_note:
                extras["day_note"] = day_note.strip()
                extras["requested_asof"] = requested.isoformat()
            self._store(asof, "post_auction", content, extras)
            return StrongPickReport(asof=asof, boards=[], stocks=[])

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
        # 早盘选股：只保留竞价上涨标的，避免自选/宇宙里弱势股占满榜单
        stocks = [s for s in stocks if float(s.get("auction_pct") or 0) > 0][:8]

        board_map: dict[str, list[float]] = {}
        for s in snaps:
            if float(s.auction_pct or 0) <= 0:
                continue
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
        stock_bits = [f"{s['symbol']}({s['auction_pct']:.1%})" for s in stocks[:4]]
        content = (
            f"【竞价强势】{asof}\n"
            f"{day_note}"
            f"板块：{' / '.join(b['board'] for b in boards)}\n"
            f"个股：{' · '.join(stock_bits)}"
        )
        self._store(
            asof,
            "post_auction",
            content,
            {
                "boards": boards,
                "stocks": stocks,
                **(
                    {"day_note": day_note.strip(), "requested_asof": requested.isoformat()}
                    if day_note
                    else {}
                ),
            },
        )
        self.alert.send("早盘·竞价强势", content, category="morning", dedupe_key=f"auction:{asof}")
        self.db.flush()
        return StrongPickReport(asof=asof, boards=boards, stocks=stocks)

    def _store(self, asof: date, stage: str, content: str, extras: dict[str, Any]) -> MorningBrief:
        cleaned = {k: v for k, v in extras.items() if v is not None}
        self.db.add(
            MorningBriefRow(
                asof=asof,
                stage=stage,
                content=content,
                extras_json=json.dumps(cleaned, ensure_ascii=False),
            )
        )
        self.db.flush()
        return MorningBrief(asof=asof, stage=stage, content=content, extras=cleaned)  # type: ignore[arg-type]
