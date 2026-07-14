"""nanobot 适配层：Skill 加载 + 简易 Agent（OpenAI 兼容）。

若未安装 hkuds-nanobot，仍可用本适配层完成投研对话与工具调用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_knowledge import KnowledgeStore
from desk_market import MarketService
from desk_strategy import StrategyRegistry


def _default_skills_root() -> Path:
    """解析 skills 目录：优先 Settings，再尝试仓库根。"""
    settings = get_settings()
    candidate = Path(settings.skills_dir)
    if candidate.exists():
        return candidate
    # 从本文件向上寻找仓库根 skills/
    here = Path(__file__).resolve()
    for parent in here.parents:
        skill_dir = parent / "skills"
        if skill_dir.is_dir():
            return skill_dir
    return candidate


class SkillLoader:
    """加载仓库 skills/*/SKILL.md。"""

    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else _default_skills_root()

    def list(self) -> list[dict[str, str]]:
        """列出 skill。"""
        if not self.root.exists():
            return []
        out = []
        for d in sorted(self.root.iterdir()):
            skill = d / "SKILL.md"
            if d.is_dir() and skill.exists():
                text = skill.read_text(encoding="utf-8")
                name = d.name
                desc = ""
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        for line in parts[1].splitlines():
                            if line.startswith("description:"):
                                desc = line.split(":", 1)[1].strip()
                out.append({"name": name, "path": str(skill), "description": desc})
        return out

    def load(self, name: str) -> str:
        """读取完整 SKILL.md。"""
        path = self.root / name / "SKILL.md"
        if not path.exists():
            raise FileNotFoundError(name)
        return path.read_text(encoding="utf-8")


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
        """DeskQuant 工具桥。"""
        if name == "get_watchlist":
            return self.market.list_watchlist()
        if name == "search_knowledge":
            return self.knowledge.search(arguments.get("query", ""))
        if name == "list_strategies":
            return [m.model_dump() for m in self.strategies.list()]
        if name == "save_strategy_draft":
            meta = self.strategies.save_agent_draft(arguments)
            return meta.model_dump()
        if name == "list_skills":
            return self.skills.list()
        return {"error": f"unknown tool {name}"}

    async def run(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """流式输出回复（简化实现）。"""
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        # 尝试 OpenAI 兼容
        if self.settings.llm_api_key:
            try:
                async for chunk in self._openai_stream(messages):
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001
                yield f"(LLM 调用失败，降级本地回复: {exc})\n\n"

        # 规则降级：策略草稿意图
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
