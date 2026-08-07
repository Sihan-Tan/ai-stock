"""投研精选 source 对人展示文案。"""

from __future__ import annotations


def research_source_label(source: str) -> str:
    """
    将内部 source 映射为中文展示名。

    @param source: morning|closing|其他
    @returns: 早盘|尾盘|原样
    """
    s = (source or "").strip().lower()
    if s == "morning":
        return "早盘"
    if s == "closing":
        return "尾盘"
    return source or ""
