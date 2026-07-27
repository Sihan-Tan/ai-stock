"""持仓建议编排。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_positions_advice.format import append_advice_section
from desk_positions_advice.llm import generate_advice_llm
from desk_positions_advice.positions import load_positions, truncate_positions
from desk_positions_advice.rules import rule_candidates

logger = logging.getLogger(__name__)


def advise_advice(
    db: Session,
    *,
    session_kind: str,
    asof: date,
    picks: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    llm_call=None,
) -> dict[str, Any]:
    """
    生成持仓建议结构化结果（供拼推送与写入 extras）。

    @param session_kind: morning | closing
    @param picks: 本次选股命中列表（可选）
    @param context: 情绪/竞价等附加上下文
    """
    settings = get_settings()
    if not getattr(settings, "positions_advice_enabled", True):
        return {"status": "disabled", "source": settings.positions_advice_source, "items": []}

    source = getattr(settings, "positions_advice_source", "live") or "live"
    mode = getattr(settings, "positions_advice_mode", "llm") or "llm"

    loaded = load_positions(db, source)
    if not loaded.get("ok"):
        err = loaded.get("error") or loaded.get("message") or "读仓失败"
        return {
            "status": "error",
            "source": source,
            "items": [],
            "section": f"持仓建议生成失败：{err}",
            "error": err,
        }

    positions = list(loaded.get("positions") or [])
    if not positions:
        return {
            "status": "empty",
            "source": source,
            "items": [],
            "section": "当前无持仓，跳过建议",
        }

    positions, truncated = truncate_positions(positions)

    pick_symbols = {
        str(p.get("symbol") or p.get("code") or "")
        for p in (picks or [])
        if isinstance(p, dict)
    }
    for p in positions:
        p["in_picks"] = p.get("symbol") in pick_symbols

    rule_cands: list[dict[str, Any]] = []
    if mode == "hybrid":
        try:
            rule_cands = rule_candidates(positions, session_kind=session_kind)
        except Exception:  # noqa: BLE001
            logger.exception("rule_candidates failed; degrade to llm")
            rule_cands = []

    facts: dict[str, Any] = {
        "asof": asof.isoformat(),
        "session_kind": session_kind,
        "mode": mode,
        "positions": positions,
        "picks_sample": (picks or [])[:12],
        "context": context or {},
    }
    if rule_cands:
        facts["rule_candidates"] = rule_cands

    llm_out = generate_advice_llm(facts, session_kind=session_kind, llm_call=llm_call)
    if llm_out.get("status") != "ok":
        err = llm_out.get("error") or "未知错误"
        return {
            "status": "error",
            "source": source,
            "items": [],
            "section": f"持仓建议生成失败：{err}",
            "error": err,
            "truncated": truncated,
        }

    return {
        "status": "ok",
        "source": source,
        "mode": mode,
        "items": llm_out.get("items") or [],
        "market_note": llm_out.get("market_note"),
        "truncated": truncated,
        "rule_candidates": rule_cands or None,
    }


__all__ = ["advise_advice", "append_advice_section"]
