"""投研会话（nanobot 适配）：Skill + 简易 Agent。

Task 6 将在此增强 OpenAI tools 循环；当前保持既有 run() 行为。
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_knowledge import KnowledgeStore
from desk_market import MarketService
from desk_strategy import StrategyRegistry

from .skills import SkillLoader
from .tools import dispatch_tool


class NanobotResearchSession:
    """
    投研会话。

    优先尝试真实 nanobot；否则走 OpenAI tools 循环 / 规则回复。
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.skills = SkillLoader()
        self.market = MarketService(db)
        self.knowledge = KnowledgeStore(db)
        self.strategies = StrategyRegistry(db)

    def skill_summary(self) -> str:
        """技能摘要。"""
        items = self.skills.list()
        return "\n".join(f"- {i['name']}: {i['description']}" for i in items)

    def run_tools(self, name: str, arguments: dict[str, Any]) -> Any:
        """DeskQuant 工具桥（白名单 dispatch）。"""
        return dispatch_tool(self.db, name, arguments)

    async def run(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """流式输出回复（简化实现）。"""
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if self.settings.llm_api_key:
            try:
                async for chunk in self._openai_stream(messages):
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001
                yield f"(LLM 调用失败，降级本地回复: {exc})\n\n"

        if "策略" in user or "yaml" in user.lower():
            draft = {
                "id": "agent_auction_chase",
                "name": "竞价高开追板草案",
                "version": "draft",
                "when": {"auction_pct": {"gte": 0.05}},
                "then": {"action": "buy"},
            }
            meta = self.strategies.save_agent_draft({"yaml_body": draft})
            yield (
                f"已加载 skills：strategy-yaml-author。\n"
                f"已保存草稿 `{meta.id}`（status=draft），请到策略管理确认 promote。\n"
                f"可用 skills:\n{self.skill_summary()}"
            )
            return

        if "知识" in user or "研报" in user:
            hits = self.knowledge.search(user)
            yield "已加载 skill knowledge-rag。\n"
            if not hits:
                yield "知识库暂无命中，请先上传文档。"
            else:
                yield "检索命中：\n" + "\n---\n".join(h["content"][:200] for h in hits)
            return

        wl = self.market.list_watchlist()
        yield (
            "nanobot 适配层在线（只读工具）。\n"
            f"Skills:\n{self.skill_summary()}\n\n"
            f"自选（{len(wl)}）：" + ", ".join(i["symbol"] for i in wl[:10])
        )

    async def _openai_stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """OpenAI 兼容非流式一次返回（简化）。"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
        )
        system = (
            "你是刻度 Desk 投研助手，运行于 nanobot 技能体系。"
            "只用只读工具；写策略只能 save_strategy_draft。"
            f"\n可用 skills:\n{self.skill_summary()}"
        )
        resp = await client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[{"role": "system", "content": system}, *messages],
        )
        yield resp.choices[0].message.content or ""
