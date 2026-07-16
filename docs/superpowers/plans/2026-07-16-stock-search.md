# 股票名称/拼音搜索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 壳层搜索支持代码/名称/拼音模糊匹配，下拉展示最符合前 6 条并点选进详情。

**Architecture:** `GET /api/market/stock/search` 查 `security_meta`（在市）+ `pypinyin`；AppShell 防抖拉候选下拉。

**Tech Stack:** FastAPI、SQLAlchemy、pypinyin、React、HeroUI、pytest、vitest

**Spec:** `docs/superpowers/specs/2026-07-16-stock-search-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `pyproject.toml` | 增加 `pypinyin` |
| `packages/market/desk_market/stock_search.py` | 拼音键、评分、search_securities |
| `apps/api/app/routes/market.py` | 注册 search 路由（注意放在 `/stock/{symbol}/...` 之前，避免 `search` 被当成 symbol） |
| `tests/test_stock_search.py` | API + 匹配单测 |
| `apps/web/src/stock/resolveSearchNavigation.ts` | 回车目标解析纯函数 |
| `apps/web/src/layout/AppShell.tsx` | 防抖下拉 UI |

---

### Task 1: search_securities + API

- [ ] 加 `pypinyin` 依赖
- [ ] 实现 `name_pinyin_keys(name) -> (full, initials)`
- [ ] 实现 `search_securities(db, q, limit=6)` 排序与过滤
- [ ] 路由 `GET /stock/search` **必须写在** `/stock/{symbol}/meta` 等动态路由之前
- [ ] pytest：贵州/gzmt/600519/空 q/limit≤6/退市排除

### Task 2: AppShell 下拉

- [ ] `resolveSearchNavigation(q, items)` 单测
- [ ] AppShell：防抖 200ms、`limit=6`、下拉点选、回车逻辑

### Task 3: 验收

- [ ] pytest + vitest；更新 spec 状态为已完成
