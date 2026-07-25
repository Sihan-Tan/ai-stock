# 投研形态手册 Implementation Plan

> **For agentic workers:** 按 Task 顺序实现；本会话可 inline 执行。

**Goal:** 新增 `pattern-playbook` skill，并在启用时对用户最新消息预检索知识库注入 system。

**Architecture:** Skill 文档引导工具使用；`session._build_system` / `run` 在 skill 启用时调用 `KnowledgeStore.search` 追加预检索区块。

**Tech Stack:** Python desk_ai、现有 KnowledgeStore、skills Markdown

---

## Task 1: Skill + 路由

- Create: `skills/pattern-playbook/SKILL.md`
- Modify: `skills/investment-research/SKILL.md` 路由表一行

## Task 2: 预检索逻辑 + 单测

- Create helper（可放 `desk_ai/pattern_prefetch.py` 或 session 内静态方法）：
  - `pattern_skill_active(skill_hint, enabled_skills, all_names) -> bool`
  - `format_knowledge_prefetch(hits) -> str`
- Modify: `session.py` `run`：build system 后若 active 且 user 非空则 search 并 append
- Test: `tests/test_pattern_prefetch.py`

## Task 3: 文档

- Spec 已写；TODO 可选一行；不强制 commit
