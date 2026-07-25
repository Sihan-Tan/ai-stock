"""投研精选：候选抽取、LLM JSON 打分、过滤落库。"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Callable, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from desk_common.contracts import ResearchPickItem, ResearchRefineReport
from desk_common.settings import get_settings
from desk_common.symbols import normalize_symbol
from desk_db.models import ClosingPick, MorningStrongPick, ResearchPick

logger = logging.getLogger(__name__)

ScorerFn = Callable[[str, str, dict[str, Any]], dict[str, Any] | None]

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _run_coro(coro: Any) -> Any:
    """
    在同步上下文中运行协程（尽量避免；精选请用 score_pick_json_sync）。

    优先新建独立 loop 并在结束前取消残留任务，减轻 httpx aclose 报错。
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            finally:
                asyncio.set_event_loop(None)
                loop.close()
    # 已在事件循环内：丢到线程，避免嵌套
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_coro, coro).result()


def _as_positive_float(value: Any) -> float | None:
    """解析为正数；失败返回 None。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0 or num != num:  # NaN
        return None
    return num


def _parse_range(data: dict[str, Any], low_key: str, high_key: str, range_key: str) -> tuple[float, float] | None:
    """
    解析价格区间：优先 low/high 字段，其次 [lo, hi] 数组。

    @returns: (low, high) 且 low <= high；非法为 None
    """
    low = _as_positive_float(data.get(low_key))
    high = _as_positive_float(data.get(high_key))
    if low is not None and high is not None:
        if low > high:
            low, high = high, low
        return low, high
    raw = data.get(range_key)
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        a = _as_positive_float(raw[0])
        b = _as_positive_float(raw[1])
        if a is None or b is None:
            return None
        return (a, b) if a <= b else (b, a)
    return None


def parse_score_payload(text: str, expected_symbol: str) -> dict[str, Any] | None:
    """
    从模型输出提取 JSON。

    必填：score/confidence（0–100）、buy 区间、target 区间、stop_loss。
    允许 markdown ```json 代码块包裹。
    """
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        score = float(data.get("score"))
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= score <= 100.0 and 0.0 <= confidence <= 100.0):
        return None
    symbol = str(data.get("symbol") or expected_symbol or "").strip()
    if not symbol:
        return None
    try:
        symbol = normalize_symbol(symbol)
    except Exception:  # noqa: BLE001
        pass

    buy = _parse_range(data, "buy_low", "buy_high", "buy_range")
    target = _parse_range(data, "target_low", "target_high", "target_range")
    stop_loss = _as_positive_float(data.get("stop_loss"))
    if buy is None or target is None or stop_loss is None:
        return None

    rationale = str(data.get("rationale") or "").strip()
    return {
        "symbol": symbol,
        "score": score,
        "confidence": confidence,
        "rationale": rationale,
        "buy_low": buy[0],
        "buy_high": buy[1],
        "target_low": target[0],
        "target_high": target[1],
        "stop_loss": stop_loss,
    }


def list_research_picks(db: Session, asof: date, source: str) -> list[dict[str, Any]]:
    """按 rank 升序返回某日某 source 的精选列表。"""
    rows = db.scalars(
        select(ResearchPick)
        .where(ResearchPick.asof == asof, ResearchPick.source == source)
        .order_by(ResearchPick.rank.asc())
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        meta: dict[str, Any] = {}
        try:
            loaded = json.loads(r.meta_json or "{}")
            if isinstance(loaded, dict):
                meta = loaded
        except json.JSONDecodeError:
            meta = {}
        out.append(
            {
                "symbol": r.symbol,
                "name": r.name,
                "score": r.score,
                "confidence": r.confidence,
                "rationale": r.rationale,
                "rank": r.rank,
                "buy_low": meta.get("buy_low"),
                "buy_high": meta.get("buy_high"),
                "target_low": meta.get("target_low"),
                "target_high": meta.get("target_high"),
                "stop_loss": meta.get("stop_loss"),
            }
        )
    return out


def maybe_auto_refine(db: Session, source: str, asof: date) -> None:
    """research_refine_auto 开启时跑精选；异常只记日志。"""
    settings = get_settings()
    if not settings.research_refine_auto:
        return
    if not settings.llm_api_key:
        logger.warning("research_refine_auto 已开但无 LLM Key，跳过")
        return
    if source not in {"morning", "closing"}:
        logger.warning("maybe_auto_refine invalid source=%s", source)
        return
    src: Literal["morning", "closing"] = "morning" if source == "morning" else "closing"
    try:
        ResearchRefineService(db).run(src, asof)
    except Exception:
        logger.exception("auto research refine failed source=%s asof=%s", source, asof)


class ResearchRefineService:
    """从早盘/尾盘候选跑投研打分，过滤后写入 research_picks。"""

    def __init__(self, db: Session, scorer: ScorerFn | None = None):
        self.db = db
        self.settings = get_settings()
        self.scorer = scorer

    def _default_scorer(self, symbol: str, name: str, context: dict[str, Any]) -> dict[str, Any] | None:
        """默认走同步 score_pick_json_sync，避免 asyncio.run + AsyncOpenAI 关环报错。"""
        from desk_ai.session import NanobotResearchSession

        return NanobotResearchSession(self.db).score_pick_json_sync(symbol, name, context)

    def _resolve_asof(self, asof: date | None) -> date:
        """解析业务日：非交易日回退上一交易日（与 morning/closing 一致）。"""
        requested = asof or date.today()
        try:
            from desk_calendar import CalendarService

            cal = CalendarService(self.db)
            if cal.is_trade_day(requested):
                return requested
            return cal.previous_trade_day(requested) or requested
        except Exception:  # noqa: BLE001
            return requested

    def _candidates(self, source: str, asof: date, limit: int) -> list[dict[str, Any]]:
        """按原 score 降序取候选；closing 按 code 去重保留 max score。"""
        if source == "morning":
            rows = self.db.scalars(
                select(MorningStrongPick)
                .where(
                    MorningStrongPick.asof == asof,
                    MorningStrongPick.pick_type == "stock",
                )
                .order_by(MorningStrongPick.score.desc())
                .limit(limit)
            ).all()
            out: list[dict[str, Any]] = []
            for r in rows:
                try:
                    symbol = normalize_symbol(r.code)
                except Exception:  # noqa: BLE001
                    symbol = r.code
                out.append(
                    {
                        "symbol": symbol,
                        "name": r.name or "",
                        "base_score": float(r.score or 0.0),
                        "meta_json": r.meta_json or "{}",
                    }
                )
            return out

        rows = self.db.scalars(
            select(ClosingPick).where(ClosingPick.asof == asof)
        ).all()
        best: dict[str, dict[str, Any]] = {}
        for r in rows:
            try:
                symbol = normalize_symbol(r.code)
            except Exception:  # noqa: BLE001
                symbol = r.code
            score = float(r.score or 0.0)
            prev = best.get(symbol)
            if prev is None or score > prev["base_score"]:
                best[symbol] = {
                    "symbol": symbol,
                    "name": r.name or "",
                    "base_score": score,
                    "meta_json": r.meta_json or "{}",
                }
        ordered = sorted(best.values(), key=lambda x: x["base_score"], reverse=True)
        return ordered[:limit]

    def _clear(self, asof: date, source: str) -> None:
        """删除同日同 source 旧精选。"""
        self.db.execute(
            delete(ResearchPick).where(
                ResearchPick.asof == asof,
                ResearchPick.source == source,
            )
        )
        self.db.flush()

    def _maybe_feishu(self, asof: date, source: str, picks: list[ResearchPickItem]) -> None:
        """成功有结果时可选飞书；失败不影响落库。"""
        if not picks:
            return
        try:
            from desk_alert import FeishuWebhookChannel

            bits = [f"{p.symbol}({p.score:.0f}/{p.confidence:.0f})" for p in picks[:8]]
            body = (
                f"【投研精选·{source}】{asof}\n"
                f"共 {len(picks)} 只：{' · '.join(bits)}"
            )
            FeishuWebhookChannel(self.db).send(
                f"投研精选·{source}",
                body,
                category="research",
                dedupe_key=f"research:{source}:{asof}",
            )
        except Exception:  # noqa: BLE001
            logger.exception("research refine feishu send failed")

    def run(
        self,
        source: Literal["morning", "closing"],
        asof: date | None = None,
        *,
        top_n: int | None = None,
        min_confidence: float | None = None,
    ) -> ResearchRefineReport:
        """
        对候选逐只打分，过滤置信度后按 score 降序取 TopN 落库。

        @param source: morning | closing
        @param asof: 业务日，默认今天（休息日回退）
        @param top_n: 覆盖本次 TopN（不写回设置）
        @param min_confidence: 覆盖本次置信度门槛
        """
        self.settings = get_settings()
        if source not in {"morning", "closing"}:
            return ResearchRefineReport(
                asof=asof or date.today(),
                source="morning",
                errors=[f"invalid_source:{source}"],
            )

        resolved = self._resolve_asof(asof)
        n = int(top_n if top_n is not None else self.settings.research_refine_top_n)
        n = max(1, min(20, n))
        min_conf = float(
            min_confidence
            if min_confidence is not None
            else self.settings.research_refine_min_confidence
        )
        min_conf = max(0.0, min(100.0, min_conf))
        max_cand = max(1, min(50, int(self.settings.research_refine_max_candidates)))

        scorer = self.scorer
        if scorer is None:
            if not self.settings.llm_api_key:
                # 无 Key：明确错误并保留既有精选，禁止清空
                return ResearchRefineReport(
                    asof=resolved,
                    source=source,
                    errors=["llm_api_key_missing"],
                )
            scorer = self._default_scorer

        candidates = self._candidates(source, resolved, max_cand)
        if not candidates:
            # 无候选时保留旧精选，避免误抹；调用方可见 no_candidates
            return ResearchRefineReport(
                asof=resolved,
                source=source,
                errors=["no_candidates"],
            )

        errors: list[str] = []
        scored: list[dict[str, Any]] = []
        for cand in candidates:
            symbol = cand["symbol"]
            name = cand.get("name") or ""
            context = {
                "source": source,
                "asof": resolved.isoformat(),
                "base_score": cand.get("base_score"),
                "name": name,
            }
            try:
                raw = scorer(symbol, name, context)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}:{type(exc).__name__}:{exc}")
                # 工具链可能弄脏 Session（如财务快照唯一键冲突）
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                continue
            if raw is None:
                errors.append(f"{symbol}:scorer_none")
                continue
            if isinstance(raw, dict):
                parsed = parse_score_payload(json.dumps(raw, ensure_ascii=False), symbol)
            else:
                parsed = parse_score_payload(str(raw), symbol)
            if parsed is None:
                errors.append(f"{symbol}:parse_failed")
                continue
            scored.append(
                {
                    **parsed,
                    "name": name,
                    "meta": {
                        **(raw if isinstance(raw, dict) else {"raw": str(raw)}),
                        "buy_low": parsed["buy_low"],
                        "buy_high": parsed["buy_high"],
                        "target_low": parsed["target_low"],
                        "target_high": parsed["target_high"],
                        "stop_loss": parsed["stop_loss"],
                    },
                }
            )

        filtered = [s for s in scored if s["confidence"] >= min_conf]
        filtered.sort(key=lambda x: x["score"], reverse=True)
        top = filtered[:n]

        # 候选均评分失败：保留旧精选，不落空表
        if not scored:
            return ResearchRefineReport(
                asof=resolved,
                source=source,
                errors=errors or ["no_scored"],
                candidates_evaluated=len(candidates),
            )

        self._clear(resolved, source)
        picks: list[ResearchPickItem] = []
        for i, item in enumerate(top, start=1):
            row = ResearchPick(
                asof=resolved,
                source=source,
                symbol=item["symbol"],
                name=item.get("name") or "",
                score=float(item["score"]),
                confidence=float(item["confidence"]),
                rationale=str(item.get("rationale") or ""),
                rank=i,
                meta_json=json.dumps(item.get("meta") or {}, ensure_ascii=False, default=str),
            )
            self.db.add(row)
            picks.append(
                ResearchPickItem(
                    symbol=row.symbol,
                    name=row.name,
                    score=row.score,
                    confidence=row.confidence,
                    rationale=row.rationale,
                    rank=row.rank,
                    buy_low=float(item["buy_low"]),
                    buy_high=float(item["buy_high"]),
                    target_low=float(item["target_low"]),
                    target_high=float(item["target_high"]),
                    stop_loss=float(item["stop_loss"]),
                )
            )
        self.db.flush()
        self._maybe_feishu(resolved, source, picks)
        return ResearchRefineReport(
            asof=resolved,
            source=source,
            picks=picks,
            errors=errors,
            candidates_evaluated=len(candidates),
        )
