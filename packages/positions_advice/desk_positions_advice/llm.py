"""持仓建议 LLM：解析与动作校验。"""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")

CLOSING_ACTIONS = frozenset({"持有", "卖出"})
MORNING_ACTIONS = frozenset({"持有", "卖出", "高抛低吸", "低吸"})


def allowed_actions(session_kind: str) -> frozenset[str]:
    """按场景返回合法动作集合。"""
    if session_kind == "morning":
        return MORNING_ACTIONS
    return CLOSING_ACTIONS


def normalize_action(action: str, session_kind: str) -> tuple[str, bool]:
    """
    校验动作；非法则回退持有。

    @returns: (最终动作, 是否发生回退)
    """
    act = str(action or "").strip()
    if act in allowed_actions(session_kind):
        return act, False
    return "持有", True


def parse_advice_payload(text: str, session_kind: str) -> dict[str, Any] | None:
    """从模型输出解析 items + market_note；非法 action 回退持有。"""
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
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    items_in = obj.get("items")
    if not isinstance(items_in, list):
        return None
    items: list[dict[str, Any]] = []
    for it in items_in:
        if not isinstance(it, dict) or not it.get("symbol"):
            continue
        action, reverted = normalize_action(str(it.get("action") or ""), session_kind)
        reason = str(it.get("reason") or "").strip() or "（无理由）"
        if reverted:
            reason = f"{reason}（动作非法已回退持有）"
        items.append(
            {
                "symbol": str(it["symbol"]),
                "action": action,
                "reason": reason,
            }
        )
    return {
        "items": items,
        "market_note": str(obj.get("market_note") or "").strip() or None,
    }
