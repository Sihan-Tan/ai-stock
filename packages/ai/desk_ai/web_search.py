"""Tavily 网页搜索（投研只读工具）。"""

from __future__ import annotations

from typing import Any

import httpx

from desk_common.settings import get_settings


def search(query: str, max_results: int = 5) -> dict[str, Any]:
    """
    调用 Tavily Search API。

    @param query: 搜索词
    @param max_results: 最多返回条数
    @returns: ``{"results": [...]}`` 或 ``{"error": "..."}``
    """
    settings = get_settings()
    api_key = (settings.tavily_api_key or "").strip()
    if not api_key:
        return {"error": "tavily_api_key not configured"}

    q = (query or "").strip()
    if not q:
        return {"error": "query is required"}

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": q,
                "max_results": max(1, min(int(max_results), 10)),
                "include_answer": False,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"tavily request failed: {exc}"}

    results = []
    for item in data.get("results") or []:
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "content": item.get("content") or item.get("snippet") or "",
            }
        )
    return {"results": results, "query": q}
