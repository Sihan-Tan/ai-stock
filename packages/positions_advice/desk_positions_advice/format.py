"""持仓建议推送文案。"""

from __future__ import annotations

from typing import Any


def append_advice_section(
    content: str,
    advice: dict[str, Any],
    *,
    name_by_symbol: dict[str, str] | None = None,
) -> str:
    """
    将持仓建议段拼到选股正文后。

    条目行格式：``{代码} {名称} {动作}｜{理由}``；名称为空则省略名称。

    @param content: 选股摘要
    @param advice: advise_advice 返回值（含 source / section 或 items）
    @param name_by_symbol: 可选代码→名称覆盖；未命中时回退 ``item.name``
    """
    source = str(advice.get("source") or "live")
    header = f"—— 持仓建议（{source}）——"
    section = str(advice.get("section") or "").strip()
    if not section:
        lines: list[str] = []
        note = str(advice.get("market_note") or "").strip()
        if note:
            lines.append(note)
        for it in advice.get("items") or []:
            if not isinstance(it, dict):
                continue
            sym = str(it.get("symbol") or "")
            name = ""
            if name_by_symbol:
                name = str(name_by_symbol.get(sym) or "").strip()
            if not name:
                name = str(it.get("name") or "").strip()
            action = str(it.get("action") or "")
            reason = str(it.get("reason") or "")
            mid = f"{sym} {name}".strip() if name else sym
            lines.append(f"{mid} {action}｜{reason}".strip())
        if advice.get("truncated"):
            lines.append("（持仓已截断，仅展示前 20 只）")
        section = "\n".join(lines) if lines else "（无建议条目）"
    return f"{content.rstrip()}\n\n{header}\n{section}"
