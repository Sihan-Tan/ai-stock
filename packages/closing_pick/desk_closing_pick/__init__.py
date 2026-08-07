"""尾盘选股：策略 buy 信号扫证券宇宙。"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_ai.refine import maybe_auto_refine
from desk_alert import FeishuWebhookChannel
from desk_calendar import CalendarService
from desk_closing_pick.screen import eval_buy_signals
from desk_common.contracts import ClosingPickReport
from desk_db.models import ClosingBriefRow, ClosingPick, SecurityMeta, StrategyRow
from desk_strategy import strategy_has_closing_role

logger = logging.getLogger(__name__)


class ClosingPickService:
    """尾盘选股：按 closing 角色策略扫在市宇宙。"""

    def __init__(self, db: Session):
        self.db = db
        self.calendar = CalendarService(db)
        self.alert = FeishuWebhookChannel(db)

    def list_closing_strategy_ids(self) -> list[str]:
        """
        最新版本策略中 params.roles 含 closing 的 ID。

        排除 archived / retired。
        """
        rows = self.db.scalars(select(StrategyRow).order_by(StrategyRow.id.desc())).all()
        seen: set[str] = set()
        out: list[str] = []
        for row in rows:
            if row.strategy_id in seen:
                continue
            seen.add(row.strategy_id)
            if row.status == "archived":
                continue
            if (row.lifecycle_stage or "") == "retired":
                continue
            try:
                params = json.loads(row.params_json or "{}")
            except json.JSONDecodeError:
                params = {}
            if strategy_has_closing_role(params):
                out.append(row.strategy_id)
        return out

    def listed_universe(self) -> list[tuple[str, str]]:
        """在市证券宇宙：(symbol, name)。"""
        rows = self.db.scalars(
            select(SecurityMeta).where(SecurityMeta.is_delisted.is_(False))
        ).all()
        return [(r.symbol, r.name or "") for r in rows]

    def run(
        self,
        asof: date | None = None,
        strategy_ids: list[str] | None = None,
    ) -> ClosingPickReport:
        """
        扫宇宙、落库 picks/brief，并尝试飞书推送。

        ``strategy_ids`` 为 None 或空列表时，使用全部 closing 角色策略；
        非空列表视为子集（可含未打标策略，供页面重跑）。

        若 ``asof`` 非交易日，回退到上一交易日扫描（摘要中注明），避免周末手动跑直接空结果。

        @param asof: 业务日
        @param strategy_ids: 可选策略列表；None/空 = 全部 closing
        """
        requested = asof or date.today()
        asof = requested
        day_note = ""
        if not self.calendar.is_trade_day(asof):
            prev = self.calendar.previous_trade_day(asof)
            day_note = f"{requested} 非交易日，已按上一交易日 {prev} 扫描。\n"
            asof = prev

        use_all_closing = not strategy_ids
        ids = (
            self.list_closing_strategy_ids()
            if use_all_closing
            else list(strategy_ids)
        )
        if not ids:
            content = (
                f"【尾盘选股】{asof}\n"
                f"{day_note}"
                "没有可跑的策略。请在策略页勾选「尾盘」，或在本页勾选策略后再跑。"
            )
            extras = {
                "strategy_ids": [],
                "hit_count": 0,
                "universe_size": 0,
                "reason": "no_strategies",
            }
            self._clear_briefs(asof)
            if requested != asof:
                self._clear_briefs(requested)
            self._store_brief(asof, content, extras)
            self.db.flush()
            return ClosingPickReport(
                asof=asof, strategy_ids=[], stocks=[], content=content
            )

        universe = self.listed_universe()
        stocks: list[dict[str, Any]] = []
        skipped_bars = 0
        skipped_strategy = 0
        evaluated = 0
        keep: set[tuple[str, str]] = set()

        for sid in ids:
            for symbol, name in universe:
                ev = eval_buy_signals(
                    self.db, strategy_id=sid, symbol=symbol, asof=asof
                )
                msg = str(ev.get("message") or "")
                if not ev.get("ok"):
                    if "insufficient bars" in msg:
                        skipped_bars += 1
                    elif "not runnable" in msg:
                        skipped_strategy += 1
                    continue
                evaluated += 1
                if not ev.get("signals"):
                    continue
                pct = float(ev.get("pct_chg") or 0)
                score = round(pct * 100, 2)
                meta = {
                    "symbol": symbol,
                    "name": name,
                    "strategy_id": sid,
                    "bar_date": ev.get("bar_date"),
                    "pct_chg": pct,
                    "last_close": ev.get("last_close"),
                    "price": ev.get("last_close"),
                    "signals": ev.get("signals"),
                }
                keep.add((sid, symbol))
                self._upsert_pick(
                    asof=asof,
                    strategy_id=sid,
                    code=symbol,
                    name=name,
                    score=score,
                    meta=meta,
                )
                stocks.append(meta)

        # 删除本 run 策略范围内未再命中的旧行
        q = select(ClosingPick).where(ClosingPick.asof == asof)
        if not use_all_closing:
            q = q.where(ClosingPick.strategy_id.in_(ids))
        for old in self.db.scalars(q).all():
            if (old.strategy_id, old.code) not in keep:
                self.db.delete(old)

        stocks.sort(key=lambda x: x.get("pct_chg") or 0, reverse=True)
        bits = [f"{s['symbol']}({s.get('strategy_id')})" for s in stocks[:6]]
        content = (
            f"【尾盘选股】{asof}\n"
            f"{day_note}"
            f"策略 {len(ids)} 个 · 宇宙 {len(universe)} 只 · 命中 {len(stocks)} 只\n"
            f"{' · '.join(bits) if bits else '无命中（策略买点未触发或 K 线不足）'}"
        )
        extras = {
            "strategy_ids": ids,
            "hit_count": len(stocks),
            "universe_size": len(universe),
            "evaluated": evaluated,
            "skipped_insufficient_bars": skipped_bars,
            "skipped_strategy_not_runnable": skipped_strategy,
            "requested_asof": requested.isoformat(),
        }
        from desk_positions_advice import advise_advice, append_advice_section

        try:
            advice = advise_advice(
                self.db,
                session_kind="closing",
                asof=asof,
                picks=stocks,
            )
            if advice.get("status") != "disabled":
                content = append_advice_section(content, advice)
                extras["positions_advice"] = {
                    k: advice.get(k)
                    for k in (
                        "status",
                        "source",
                        "mode",
                        "items",
                        "market_note",
                        "truncated",
                        "error",
                        "section",
                    )
                    if advice.get(k) is not None
                }
        except Exception as exc:  # noqa: BLE001
            logger.exception("positions advice failed after closing pick")
            advice = {
                "status": "error",
                "source": "live",
                "section": f"持仓建议生成失败：{exc}",
                "items": [],
                "error": str(exc),
            }
            content = append_advice_section(content, advice)
            extras["positions_advice"] = {
                k: advice.get(k)
                for k in ("status", "source", "items", "error", "section")
                if advice.get(k) is not None
            }
        self._clear_briefs(asof)
        if requested != asof:
            self._clear_briefs(requested)
        self._store_brief(asof, content, extras)
        try:
            self.alert.send(
                "尾盘选股",
                content,
                category="closing",
                dedupe_key=f"closing:{asof}",
            )
        except Exception:  # noqa: BLE001
            pass
        self.db.flush()
        if stocks:
            maybe_auto_refine(self.db, "closing", asof)
        return ClosingPickReport(
            asof=asof, strategy_ids=ids, stocks=stocks, content=content
        )

    def _upsert_pick(
        self,
        *,
        asof: date,
        strategy_id: str,
        code: str,
        name: str,
        score: float,
        meta: dict[str, Any],
    ) -> ClosingPick:
        """
        按 (asof, strategy_id, code) upsert 尾盘候选。

        @param asof: 业务日
        @param strategy_id: 命中策略
        @param code: 证券代码
        @param name: 证券名
        @param score: 分数
        @param meta: 写入 meta_json 的字典
        @returns: 落库行
        """
        row = self.db.scalar(
            select(ClosingPick).where(
                ClosingPick.asof == asof,
                ClosingPick.strategy_id == strategy_id,
                ClosingPick.code == code,
            )
        )
        if row is None:
            row = ClosingPick(
                asof=asof,
                strategy_id=strategy_id,
                pick_type="stock",
                code=code,
            )
            self.db.add(row)
        row.name = name
        row.score = score
        row.meta_json = json.dumps(meta, ensure_ascii=False)
        return row

    def _clear_briefs(self, asof: date) -> None:
        """删除同日 closing 阶段 brief，避免重跑堆积。"""
        rows = self.db.scalars(
            select(ClosingBriefRow).where(
                ClosingBriefRow.asof == asof,
                ClosingBriefRow.stage == "closing",
            )
        ).all()
        for row in rows:
            self.db.delete(row)

    def _store_brief(
        self, asof: date, content: str, extras: dict[str, Any]
    ) -> None:
        """写入 ClosingBriefRow。"""
        self.db.add(
            ClosingBriefRow(
                asof=asof,
                stage="closing",
                content=content,
                extras_json=json.dumps(extras, ensure_ascii=False),
            )
        )
        self.db.flush()
