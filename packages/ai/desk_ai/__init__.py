"""nanobot 适配层：Skill 加载 + 简易 Agent（OpenAI 兼容）。

若未安装 hkuds-nanobot，仍可用本适配层完成投研对话与工具调用。
"""

from __future__ import annotations

from desk_ai.refine import (
    ResearchRefineService,
    list_research_picks,
    maybe_auto_refine,
    parse_score_payload,
)
from desk_ai.session import NanobotResearchSession
from desk_ai.skills import SkillLoader

__all__ = [
    "NanobotResearchSession",
    "SkillLoader",
    "ResearchRefineService",
    "parse_score_payload",
    "list_research_picks",
    "maybe_auto_refine",
]
