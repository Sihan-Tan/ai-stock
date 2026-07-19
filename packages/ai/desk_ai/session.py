"""投研会话（nanobot 适配）：Skill + OpenAI tools 循环。"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_knowledge import KnowledgeStore
from desk_market import MarketService
from desk_strategy import StrategyRegistry

from .skills import SkillLoader
from .tools import TOOL_SPECS, dispatch_tool

_TOOL_RESULT_MAX = 12_000
_MAX_ITERATIONS = 8


class NanobotResearchSession:
    """
    投研会话。

    优先走 OpenAI 兼容 tools 循环；无 API Key 时提示配置，并保留策略/知识关键词降级。
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

    async def _chat_create(self, **kwargs: Any) -> Any:
        """调用 OpenAI 兼容 chat.completions.create（测试可注入替换）。"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
        )
        return await client.chat.completions.create(**kwargs)

    def _build_system(self, skill_hint: str | None) -> str:
        """组装 system：身份 + skills 摘要 + 硬约束；可选加载 skill 全文。"""
        parts = [
            "你是刻度 Desk 投研助手，运行于 nanobot 技能体系。",
            "只用只读工具；写策略只能 save_strategy_draft。",
            "数字必须来自工具，禁止编造财务或估值数据。",
            "禁止下单，禁止修改交易开关或 Kill Switch。",
            f"可用 skills:\n{self.skill_summary()}",
        ]
        if skill_hint:
            try:
                parts.append(f"\n--- skill: {skill_hint} ---\n{self.skills.load(skill_hint)}")
            except (FileNotFoundError, OSError):
                pass
        return "\n".join(parts)

    @staticmethod
    def _truncate_tool_result(value: Any) -> str:
        """将工具结果序列化为 JSON；超长时仍返回可解析对象（带 truncated 标记）。"""
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = json.dumps({"error": "unserializable", "repr": str(value)[:2000]}, ensure_ascii=False)
        if len(text) <= _TOOL_RESULT_MAX:
            return text
        # 保持合法 JSON，避免截断破坏 tools 循环解析
        preview = text[: max(0, _TOOL_RESULT_MAX - 120)]
        return json.dumps(
            {"truncated": True, "preview": preview, "original_chars": len(text)},
            ensure_ascii=False,
        )

    @staticmethod
    def _tool_calls_payload(tool_calls: Any) -> list[dict[str, Any]]:
        """将 SDK tool_calls 转为可 append 的 message 片段。"""
        out: list[dict[str, Any]] = []
        for tc in tool_calls or []:
            out.append(
                {
                    "id": tc.id,
                    "type": getattr(tc, "type", "function") or "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
            )
        return out

    @staticmethod
    def _format_llm_error(exc: BaseException) -> str:
        """
        将 LLM / 网络异常转为可读中文提示（避免流式连接被异常直接掐断）。

        @param exc: 异常
        """
        name = type(exc).__name__
        text = str(exc)
        lower = text.lower()
        if name in {"AuthenticationError", "PermissionDeniedError"} or "401" in text or "authentication" in lower:
            return (
                "LLM 认证失败（API Key 无效或已过期）。"
                "请到「设置 → LLM」更新 Key 后重试。"
                f"\n详情：{text[:300]}"
            )
        if name in {"RateLimitError"} or "429" in text or "rate limit" in lower:
            return f"LLM 请求过于频繁，请稍后重试。\n详情：{text[:300]}"
        if name in {"APIConnectionError", "APITimeoutError", "ConnectError", "TimeoutError"}:
            return (
                "无法连接 LLM 服务，请检查网络与「设置 → LLM」中的 Base URL。"
                f"\n详情：{text[:300]}"
            )
        return f"LLM 调用失败（{name}）：{text[:400]}"

    async def run(
        self,
        messages: list[dict[str, Any]],
        skill_hint: str | None = None,
    ) -> AsyncIterator[str]:
        """流式输出：tools 循环或无 Key 时的提示/关键词降级。"""
        user = next((m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"), "")
        if not isinstance(user, str):
            user = str(user)

        if not self.settings.llm_api_key:
            async for chunk in self._fallback_without_llm(user):
                yield chunk
            return

        system = self._build_system(skill_hint)
        working: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]

        try:
            for _ in range(_MAX_ITERATIONS):
                resp = await self._chat_create(
                    model=self.settings.llm_model,
                    messages=working,
                    tools=TOOL_SPECS,
                    tool_choice="auto",
                )
                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None) or None
                content = getattr(msg, "content", None)

                if tool_calls:
                    working.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": self._tool_calls_payload(tool_calls),
                        }
                    )
                    for tc in tool_calls:
                        name = tc.function.name
                        yield f"[tool:{name}]\n"
                        raw_args = tc.function.arguments or "{}"
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}
                        if not isinstance(args, dict):
                            args = {}
                        try:
                            # FinancialService 内部对 QMT/akshare 已加超时，避免永久卡住
                            result = dispatch_tool(self.db, name, args)
                        except Exception as tool_exc:  # noqa: BLE001
                            result = {"error": f"{type(tool_exc).__name__}: {tool_exc}"}
                        working.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": self._truncate_tool_result(result),
                            }
                        )
                    continue

                if content:
                    yield content
                    return

                return

            yield "（已达工具调用轮次上限，请缩小问题后重试。）"
        except Exception as exc:  # noqa: BLE001
            yield self._format_llm_error(exc)

    async def _fallback_without_llm(self, user: str) -> AsyncIterator[str]:
        """无 API Key：提示配置 LLM；可选策略/知识关键词降级（不假装五步法）。"""
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

        yield (
            "未配置 LLM API Key。请到设置页填写 LLM（OpenAI 兼容 / DeepSeek 等）后再使用投研对话。"
            f"\n可用 skills:\n{self.skill_summary()}"
        )
