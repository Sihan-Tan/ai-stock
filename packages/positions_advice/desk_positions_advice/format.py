"""持仓建议推送文案。"""

from __future__ import annotations

from typing import Any


def append_advice_section(content: str, advice: dict[str, Any]) -> str:
    """
    将持仓建议段拼到选股正文后。

    @param content: 选股摘要
    @param advice: advise_advice 返回值（含 source / section 或 items）
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
            sym = it.get("symbol") or ""
            action = it.get("action") or ""
            reason = it.get("reason") or ""
            lines.append(f"{sym} {action}｜{reason}")
        if advice.get("truncated"):
            lines.append("（持仓已截断，仅展示前 20 只）")
        section = "\n".join(lines) if lines else "（无建议条目）"
    return f"{content.rstrip()}\n\n{header}\n{section}"
