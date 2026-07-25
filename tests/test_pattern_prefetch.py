"""pattern-playbook 预检索辅助测试。"""

from __future__ import annotations

from desk_ai.pattern_prefetch import (
    PATTERN_PLAYBOOK_SKILL,
    format_knowledge_prefetch,
    pattern_skill_active,
    prefetch_pattern_knowledge,
)


def test_pattern_skill_active_hint():
    names = {PATTERN_PLAYBOOK_SKILL, "write-report"}
    assert pattern_skill_active(PATTERN_PLAYBOOK_SKILL, [], names) is True


def test_pattern_skill_active_enabled_list():
    names = {PATTERN_PLAYBOOK_SKILL, "write-report"}
    assert pattern_skill_active(None, [PATTERN_PLAYBOOK_SKILL], names) is True
    assert pattern_skill_active(None, ["write-report"], names) is False


def test_pattern_skill_active_all_enabled():
    names = {PATTERN_PLAYBOOK_SKILL}
    assert pattern_skill_active(None, None, names) is True


def test_pattern_skill_active_missing_skill():
    assert pattern_skill_active(PATTERN_PLAYBOOK_SKILL, None, {"write-report"}) is False


def test_format_knowledge_prefetch_empty():
    text = format_knowledge_prefetch([])
    assert "无命中" in text
    assert "pattern-playbook" in text


def test_format_knowledge_prefetch_hits():
    text = format_knowledge_prefetch(
        [
            {
                "title": "形态手册",
                "chunk_index": 0,
                "score": 3.0,
                "content": "头肩顶：左肩、头部、右肩，颈线跌破确认。",
            }
        ]
    )
    assert "头肩顶" in text
    assert "形态手册" in text


def test_prefetch_empty_query():
    """空 query 不访问库。"""
    assert prefetch_pattern_knowledge(object(), "  ") == ""
