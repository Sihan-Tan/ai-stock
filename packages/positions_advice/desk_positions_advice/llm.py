"""持仓建议 LLM：解析与动作校验。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from desk_common.settings import get_settings

logger = logging.getLogger(__name__)
LlmFn = Callable[[str, str], str]

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


def _default_llm_call(system: str, user: str) -> str:
    """同步调用 OpenAI 兼容 Chat。"""
    from openai import OpenAI
    from desk_ai.session import resolve_llm_model

    settings = get_settings()
    if not settings.llm_api_key:
        raise ValueError("未配置 LLM API Key")
    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
        timeout=60,
    )
    model = resolve_llm_model(settings.llm_provider, settings.llm_model)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return str(getattr(resp.choices[0].message, "content", None) or "")


def generate_advice_llm(
    facts: dict[str, Any],
    *,
    session_kind: str,
    llm_call: LlmFn | None = None,
) -> dict[str, Any]:
    """
    一次 LLM 生成持仓建议。

    @returns: {status, items?, market_note?, error?}
    """
    settings = get_settings()
    if llm_call is None and not settings.llm_api_key:
        return {"status": "error", "error": "未配置 LLM API Key", "items": []}

    actions = "、".join(sorted(allowed_actions(session_kind)))
    label = "早盘竞价后" if session_kind == "morning" else "尾盘选股后"
    system = (
        f"你是刻度 Desk {label}持仓建议助手。"
        "根据预取事实给出每只持仓的操作建议与简短理由，禁止编造未给出的数字。"
        "只输出一个 JSON 对象。"
    )
    user = (
        f"场景={session_kind}。合法 action 仅限：{actions}。\n"
        f"事实：\n{json.dumps(facts, ensure_ascii=False, default=str)}\n\n"
        '输出：{"items":[{"symbol":"...","action":"...","reason":"..."}],'
        '"market_note":"可选一句市场总评"}'
    )
    call = llm_call or _default_llm_call
    try:
        raw = call(system, user)
    except Exception as exc:  # noqa: BLE001
        logger.exception("positions advice llm failed")
        return {"status": "error", "error": str(exc), "items": []}

    parsed = parse_advice_payload(raw, session_kind)
    if not parsed:
        return {
            "status": "error",
            "error": "模型输出无法解析为 JSON",
            "items": [],
            "raw_preview": (raw or "")[:300],
        }
    return {
        "status": "ok",
        "items": parsed["items"],
        "market_note": parsed.get("market_note"),
    }
