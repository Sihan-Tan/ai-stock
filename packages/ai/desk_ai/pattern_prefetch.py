"""形态手册 skill：启用时预检索知识库并格式化注入 system。"""

from __future__ import annotations

from typing import Any, Iterable

PATTERN_PLAYBOOK_SKILL = "pattern-playbook"
_PREFETCH_TOP_K = 5
_CHUNK_PREVIEW_MAX = 700
_SECTION_MAX = 4500


def pattern_skill_active(
    skill_hint: str | None,
    enabled_skills: list[str] | None,
    all_names: Iterable[str],
) -> bool:
    """判断是否应做形态知识预检索。

    Args:
        skill_hint: 快捷指定的 skill。
        enabled_skills: 用户启用列表；``None`` 表示全部可用。
        all_names: 仓库中已有 skill 名集合。

    Returns:
        当 ``pattern-playbook`` 存在且（hint 指向它或落在启用列表）时为 True。
    """
    names = set(all_names)
    if PATTERN_PLAYBOOK_SKILL not in names:
        return False
    if skill_hint == PATTERN_PLAYBOOK_SKILL:
        return True
    if enabled_skills is None:
        return True
    return PATTERN_PLAYBOOK_SKILL in enabled_skills


def format_knowledge_prefetch(hits: list[dict[str, Any]]) -> str:
    """将检索命中格式化为 system 区块正文。

    Args:
        hits: ``KnowledgeStore.search`` 返回列表。

    Returns:
        Markdown 文本；无命中时给出上传提示。
    """
    header = (
        "## 知识库预检索（pattern-playbook）\n"
        "以下片段来自知识库，请优先引用；可再调用 search_knowledge 换关键词。"
        "形态识别主观，不构成投资建议。\n"
    )
    if not hits:
        return (
            header
            + "\n（无命中）请提示用户在知识库上传形态/走势资料，并打标签如 `形态,技术分析`。\n"
        )

    parts: list[str] = [header]
    used = len(header)
    for h in hits:
        title = str(h.get("title") or h.get("doc_id") or "未命名")
        idx = h.get("chunk_index", "")
        score = h.get("score", "")
        content = str(h.get("content") or "").strip()
        if len(content) > _CHUNK_PREVIEW_MAX:
            content = content[:_CHUNK_PREVIEW_MAX] + "…"
        block = f"\n### {title} · chunk {idx}（score={score}）\n{content}\n"
        if used + len(block) > _SECTION_MAX:
            parts.append("\n（其余命中已省略）\n")
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


def prefetch_pattern_knowledge(
    db: Any,
    user_query: str,
    *,
    top_k: int = _PREFETCH_TOP_K,
) -> str:
    """对用户最新消息做知识库检索并格式化。

    Args:
        db: SQLAlchemy Session。
        user_query: 用户最新一条文本。
        top_k: 返回条数。

    Returns:
        可追加到 system 的 Markdown；query 为空时返回空串。
    """
    q = (user_query or "").strip()
    if not q:
        return ""
    try:
        from desk_knowledge import KnowledgeStore

        hits = KnowledgeStore(db).search(q, top_k=top_k)
    except Exception:  # noqa: BLE001 — 预检索失败不阻断对话
        return (
            "## 知识库预检索（pattern-playbook）\n"
            "（检索失败，可稍后手动调用 search_knowledge。）\n"
        )
    return format_knowledge_prefetch(hits if isinstance(hits, list) else [])
