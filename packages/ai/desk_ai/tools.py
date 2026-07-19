"""投研只读 tools：OpenAI schema + 白名单 dispatch。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from desk_knowledge import KnowledgeStore
from desk_market import MarketService
from desk_market.financials import FinancialService
from desk_strategy import StrategyRegistry

from . import web_search as web_search_mod
from .skills import SkillLoader

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "get_watchlist",
        "list_strategies",
        "list_skills",
        "search_knowledge",
        "save_strategy_draft",
        "get_financials",
        "peer_compare",
        "get_valuation",
        "web_search",
        "save_research_note",
    }
)


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict:
    """构造 OpenAI tools function schema 条目。"""
    params: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        params["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": params,
        },
    }


TOOL_SPECS: list[dict[str, Any]] = [
    _fn("get_watchlist", "列出自选股", {}),
    _fn("list_strategies", "列出策略元数据", {}),
    _fn("list_skills", "列出可用 skills", {}),
    _fn(
        "search_knowledge",
        "检索知识库",
        {"query": {"type": "string", "description": "检索关键词"}},
        ["query"],
    ),
    _fn(
        "save_strategy_draft",
        "保存策略 YAML 草稿（需用户明确要求写策略时才用）",
        {
            "yaml_body": {"description": "策略 YAML/对象"},
            "id": {"type": "string"},
            "name": {"type": "string"},
        },
    ),
    _fn(
        "get_financials",
        "单股财务指标与报表（只读）",
        {
            "symbol": {"type": "string", "description": "股票代码"},
            "years": {"type": "integer", "description": "最近若干年", "default": 5},
        },
        ["symbol"],
    ),
    _fn(
        "peer_compare",
        "同行财务横向对比（只读）",
        {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "对比标的列表",
            },
            "years": {"type": "integer", "default": 5},
        },
        ["symbols"],
    ),
    _fn(
        "get_valuation",
        "估值 PE/PB/PS 与分位（只读）",
        {
            "symbol": {"type": "string"},
            "peers": {"type": "array", "items": {"type": "string"}},
        },
        ["symbol"],
    ),
    _fn(
        "web_search",
        "Tavily 网页搜索（需配置 tavily_api_key）",
        {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        ["query"],
    ),
    _fn(
        "save_research_note",
        "保存投研笔记到知识库",
        {
            "title": {"type": "string"},
            "body": {"type": "string"},
            "symbols": {"type": "array", "items": {"type": "string"}},
        },
        ["title", "body"],
    ),
]


def dispatch_tool(db: Session, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """
    白名单工具分发；未知工具返回 error。

    @param db: SQLAlchemy Session
    @param name: 工具名
    @param arguments: 工具参数
    """
    args = dict(arguments or {})
    if name not in ALLOWED_TOOLS:
        return {"error": f"unknown tool {name}"}

    if name == "get_watchlist":
        return MarketService(db).list_watchlist()

    if name == "list_strategies":
        return [m.model_dump() for m in StrategyRegistry(db).list()]

    if name == "list_skills":
        return SkillLoader().list()

    if name == "search_knowledge":
        return KnowledgeStore(db).search(args.get("query", ""))

    if name == "save_strategy_draft":
        meta = StrategyRegistry(db).save_agent_draft(args)
        return meta.model_dump()

    if name == "get_financials":
        years = int(args.get("years") or 5)
        return FinancialService(db).get_financials(str(args.get("symbol") or ""), years=years)

    if name == "peer_compare":
        symbols = args.get("symbols") or []
        if not isinstance(symbols, list):
            return {"error": "symbols must be a list"}
        years = int(args.get("years") or 5)
        return FinancialService(db).peer_compare([str(s) for s in symbols], years=years)

    if name == "get_valuation":
        peers = args.get("peers")
        peer_list = [str(p) for p in peers] if isinstance(peers, list) else None
        return FinancialService(db).get_valuation(str(args.get("symbol") or ""), peers=peer_list)

    if name == "web_search":
        max_results = int(args.get("max_results") or 5)
        return web_search_mod.search(str(args.get("query") or ""), max_results=max_results)

    if name == "save_research_note":
        symbols = args.get("symbols") or []
        if not isinstance(symbols, list):
            symbols = []
        tags = ",".join(str(s) for s in symbols)
        return KnowledgeStore(db).upsert(
            title=str(args.get("title") or ""),
            content=str(args.get("body") or ""),
            doc_type="research_note",
            tags=tags,
        )

    return {"error": f"unknown tool {name}"}
