"""知识库正文切片。"""

from __future__ import annotations


def chunk_text(content: str, size: int = 800, overlap: int = 100) -> list[str]:
    """按固定窗口切分正文，相邻块重叠 overlap 字。

    Args:
        content: 原始正文。
        size: 每块目标长度。
        overlap: 相邻块重叠长度。

    Returns:
        非空切片列表；空正文返回 []。
    """
    content = content.strip()
    if not content:
        return []
    if size <= 0:
        return [content]
    step = max(1, size - overlap)
    parts: list[str] = []
    i = 0
    n = len(content)
    while i < n:
        parts.append(content[i : i + size])
        if i + size >= n:
            break
        i += step
    return parts
