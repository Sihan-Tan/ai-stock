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

# DeepSeek 已弃用旧模型名；本地 .env 仍写 deepseek-chat 时自动映射
_DEEPSEEK_MODEL_ALIASES = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-pro",
}


def resolve_llm_model(provider: str, model: str) -> str:
    """
    解析实际调用的模型 ID。

    @param provider: llm_provider
    @param model: 配置中的模型名
    """
    name = (model or "").strip()
    if (provider or "").strip().lower() == "deepseek":
        return _DEEPSEEK_MODEL_ALIASES.get(name, name or "deepseek-v4-flash")
    return name


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
        try:
            return await client.chat.completions.create(**kwargs)
        finally:
            await client.close()

    def _chat_create_sync(self, **kwargs: Any) -> Any:
        """同步调用 chat.completions.create（精选打分用）。"""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
        )
        try:
            return client.chat.completions.create(**kwargs)
        finally:
            client.close()

    def _build_system(
        self,
        skill_hint: str | None = None,
        enabled_skills: list[str] | None = None,
    ) -> str:
        """
        组装 system：身份 + 启用 skills 摘要/全文 + 硬约束。

        @param skill_hint: 优先强调的 skill（快捷提示）
        @param enabled_skills: 用户勾选启用的 skill 名；None 表示全部可用（仅摘要）
        """
        all_items = self.skills.list()
        all_names = {i["name"] for i in all_items}
        if enabled_skills is None:
            enabled = [i["name"] for i in all_items]
        else:
            enabled = [n for n in enabled_skills if n in all_names]
        # hint 优先加载，且并入启用列表
        ordered: list[str] = []
        if skill_hint and skill_hint in all_names:
            ordered.append(skill_hint)
        for name in enabled:
            if name not in ordered:
                ordered.append(name)

        summary_lines = []
        for item in all_items:
            if item["name"] in ordered:
                summary_lines.append(f"- {item['name']}: {item['description']}")
        summary = "\n".join(summary_lines) if summary_lines else "（当前未启用任何 skill）"

        parts = [
            "你是刻度 Desk 投研助手，运行于 nanobot 技能体系。",
            "只用只读工具；写策略只能 save_strategy_draft。",
            "数字必须来自工具，禁止编造财务或估值数据。",
            "禁止下单，禁止修改交易开关或 Kill Switch。",
            f"已启用 skills:\n{summary}",
        ]
        # 加载启用 skill 全文（控制总长度，避免撑爆上下文）
        budget = 24_000
        used = 0
        for name in ordered:
            try:
                body = self.skills.load(name)
            except (FileNotFoundError, OSError):
                continue
            chunk = f"\n--- skill: {name} ---\n{body}"
            if used + len(chunk) > budget:
                parts.append(f"\n--- skill: {name} ---\n（正文过长已省略，请按摘要执行）")
                break
            parts.append(chunk)
            used += len(chunk)
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
        enabled_skills: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """流式输出：tools 循环或无 Key 时的提示/关键词降级。"""
        user = next((m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"), "")
        if not isinstance(user, str):
            user = str(user)

        if not self.settings.llm_api_key:
            async for chunk in self._fallback_without_llm(user):
                yield chunk
            return

        system = self._build_system(skill_hint=skill_hint, enabled_skills=enabled_skills)
        all_names = {i["name"] for i in self.skills.list()}
        from desk_ai.pattern_prefetch import pattern_skill_active, prefetch_pattern_knowledge

        if pattern_skill_active(skill_hint, enabled_skills, all_names):
            block = prefetch_pattern_knowledge(self.db, user)
            if block:
                system = f"{system}\n\n{block}"
        working: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]
        tool_specs = tools if tools is not None else TOOL_SPECS
        model = resolve_llm_model(self.settings.llm_provider, self.settings.llm_model)

        try:
            for _ in range(_MAX_ITERATIONS):
                resp = await self._chat_create(
                    model=model,
                    messages=working,
                    tools=tool_specs,
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

    def score_picks_batch_sync(
        self,
        batch: list[dict[str, Any]],
        *,
        source: str,
        asof: date | str,
    ) -> dict[str, dict[str, Any]]:
        """
        分批精选评分：注入预取事实，单次无工具 LLM，返回 symbol→payload。

        @param batch: 含 symbol/name/facts/base_score 的候选
        @param source: morning|closing
        @param asof: 业务日
        """
        from datetime import date as date_cls

        from desk_ai.refine import parse_score_payload_list

        if not self.settings.llm_api_key:
            return {}
        if not batch:
            return {}

        asof_s = asof.isoformat() if isinstance(asof, date_cls) else str(asof)
        payload = []
        symbols: list[str] = []
        for item in batch:
            symbol = str(item.get("symbol") or "")
            symbols.append(symbol)
            payload.append(
                {
                    "symbol": symbol,
                    "name": item.get("name") or "",
                    "base_score": item.get("base_score"),
                    "facts": item.get("facts") or {},
                }
            )

        system = (
            "你是刻度 Desk 精选评分助手。"
            "根据用户给出的预取事实对候选打分并给出价格计划。"
            "禁止编造财务数字；事实缺失时降低 confidence。"
            "禁止调用工具；禁止输出 JSON 以外的文字。"
        )
        user = (
            f"场次={source} 日期={asof_s}。对下列 {len(payload)} 只股票评分。\n"
            f"候选事实：{json.dumps(payload, ensure_ascii=False, default=str)}\n"
            "只输出一个 JSON 数组，每项字段："
            '{"symbol","score","confidence","rationale",'
            '"buy_low","buy_high","target_low","target_high","stop_loss"}；'
            "score/confidence 为 0-100；价格为正数且 buy_low<=buy_high、target_low<=target_high。"
        )
        model = resolve_llm_model(self.settings.llm_provider, self.settings.llm_model)
        resp = self._chat_create_sync(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # 无 tools：一次往返
        )
        content = getattr(resp.choices[0].message, "content", None) or ""
        return parse_score_payload_list(str(content), symbols)

    def score_pick_json_sync(
        self,
        symbol: str,
        name: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        单股精选评分：优先用 context.facts 一次无工具调用；无事实时短工具环。

        @param symbol: 标的代码
        @param name: 名称
        @param context: 候选上下文（可含 facts）
        @returns: 解析后的 score payload；失败抛 RuntimeError 或返回 None
        """
        if not self.settings.llm_api_key:
            return None
        from desk_ai.refine import parse_score_payload
        from desk_ai.tools import READONLY_TOOL_SPECS

        facts = context.get("facts") if isinstance(context, dict) else None
        model = resolve_llm_model(self.settings.llm_provider, self.settings.llm_model)

        # 快路径：已有预取事实 → 单次无工具 LLM
        if isinstance(facts, dict) and facts:
            system = (
                "你是刻度 Desk 精选评分助手。根据预取事实打分并给出价格计划。"
                "禁止编造数字；禁止调用工具；只输出一行 JSON。"
            )
            prompt = (
                f"对 {symbol}（{name}）评分。上下文：{json.dumps(context, ensure_ascii=False, default=str)}。"
                "字段："
                '{"symbol","score","confidence","rationale",'
                '"buy_low","buy_high","target_low","target_high","stop_loss"}；'
                "score/confidence 0-100；价格为正且区间合法。"
            )
            try:
                resp = self._chat_create_sync(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                )
                content = getattr(resp.choices[0].message, "content", None)
                if content:
                    parsed = parse_score_payload(str(content), symbol)
                    if parsed is not None:
                        return parsed
                    raise RuntimeError(f"未解析到评分 JSON：{str(content).strip()[:240]}")
                return None
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(self._format_llm_error(exc)) from exc

        # 降级：仅 get_financials / get_valuation，最多 3 轮
        prompt = (
            f"对 {symbol}（{name}）做精选评分。上下文：{json.dumps(context, ensure_ascii=False)}。"
            "只允许调用 get_valuation 或 get_financials；禁止其它工具。"
            "必须给出买入区间、目标价区间、止损价。"
            "最终只输出一行 JSON："
            '{"symbol","score","confidence","rationale",'
            '"buy_low","buy_high","target_low","target_high","stop_loss"}。'
        )
        system = (
            "你是刻度 Desk 精选评分助手。只用估值/财务只读工具，禁止编造数字。"
            "尽快结束工具调用并输出 JSON。"
        )
        working: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        max_iters = 3
        try:
            for _ in range(max_iters):
                resp = self._chat_create_sync(
                    model=model,
                    messages=working,
                    tools=READONLY_TOOL_SPECS,
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
                        raw_args = tc.function.arguments or "{}"
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}
                        if not isinstance(args, dict):
                            args = {}
                        try:
                            result = dispatch_tool(self.db, tc.function.name, args)
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
                    parsed = parse_score_payload(content, symbol)
                    if parsed is not None:
                        return parsed
                    stripped = str(content).strip()
                    if stripped:
                        raise RuntimeError(f"未解析到评分 JSON：{stripped[:240]}")
                    return None
                return None
            raise RuntimeError("精选评分已达工具调用轮次上限")
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(self._format_llm_error(exc)) from exc

    async def score_pick_json(
        self,
        symbol: str,
        name: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        受控投研评分：启用 investment-research / financial-analysis / valuation；
        要求最终只输出一行 JSON。

        @param symbol: 标的代码
        @param name: 名称
        @param context: 候选上下文（source/asof/base_score 等）
        @returns: 解析后的 score payload，失败为 None
        """
        # 异步入口也走同步实现，避免 AsyncOpenAI 在 asyncio.run 关环时 aclose 报错
        return self.score_pick_json_sync(symbol, name, context)

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
