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
        "get_candlestick_patterns",
    }
)

# 精选评分允许的只读工具（禁止写草稿/笔记）
# 注意：默认精选路径已改为「预取事实 + 无工具分批 LLM」，下列集合仅作兼容/降级
READONLY_SCORE_TOOLS: frozenset[str] = frozenset(
    {
        "get_financials",
        "get_valuation",
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
        "检索知识库（模式取自全局 knowledge_retrieval 设置）",
        {
            "query": {"type": "string", "description": "检索关键词"},
            "top_k": {"type": "integer", "description": "返回条数，默认 5"},
        },
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
        "get_candlestick_patterns",
        "扫描标的近 N 日 TA-Lib K 线形态（CDL）；可筛选形态名/中文短名；only_hits 默认只返回非零信号",
        {
            "symbol": {"type": "string", "description": "股票代码"},
            "lookback_bars": {
                "type": "integer",
                "description": "回看交易日根数，默认 30，范围 5–120",
            },
            "patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选：CDLENGULFING / ENGULFING / 吞没 等；空=全部 CDL",
            },
            "only_hits": {
                "type": "boolean",
                "description": "仅返回非 0 信号，默认 true",
            },
        },
        ["symbol"],
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

READONLY_TOOL_SPECS: list[dict[str, Any]] = [
    spec
    for spec in TOOL_SPECS
    if (spec.get("function") or {}).get("name") in READONLY_SCORE_TOOLS
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
        top_k = int(args.get("top_k") or 5)
        # mode=None → Store 内取 get_settings().knowledge_retrieval
        return KnowledgeStore(db).search(str(args.get("query") or ""), top_k=top_k)

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

    if name == "get_candlestick_patterns":
        from desk_ai.candlestick_patterns import get_candlestick_patterns

        patterns = args.get("patterns")
        if patterns is not None and not isinstance(patterns, list):
            return {"error": "patterns must be a list of strings"}
        only_hits = args.get("only_hits")
        if only_hits is None:
            only_hits = True
        return get_candlestick_patterns(
            db,
            str(args.get("symbol") or ""),
            lookback_bars=int(args.get("lookback_bars") or 30),
            patterns=[str(p) for p in patterns] if patterns else None,
            only_hits=bool(only_hits),
        )

    return {"error": f"unknown tool {name}"}
