---
name: investment-research
description: 投研场景索引与路由；不确定用户意图时先读本 skill，再切换到对应专项 skill。
---

# investment-research

投研对话入口。根据用户问题选择专项 skill，禁止编造财务或估值数据。

## 场景路由表

| 用户意图 | 路由 skill | 主要工具 |
|----------|------------|----------|
| 单股财务、盈利能力、负债、现金流 | `financial-analysis` | `get_financials` |
| 同行对比、横向财务比较 | `peer-compare` | `peer_compare` |
| 估值、PE/PB/PS、分位、相对估值 | `valuation` | `get_valuation` |
| 深度研报、五步法、护城河、预期差 | `write-report` | `get_financials`、`get_valuation`、`web_search`、`search_knowledge`、`save_research_note` |
| 检索已有研报/笔记 | `knowledge-rag` | `search_knowledge` |

## 工作流

1. 判断场景，加载对应 skill 全文并按其步骤执行。
2. 数字必须来自 Desk 只读工具；工具返回 `error` 时如实说明，不得猜测。
3. 禁止下单、禁止修改风控；写策略草稿仅在用户明确要求时使用 `save_strategy_draft`（本 skill 不涉及）。

## 示例问法

- 「茅台最近五年 ROE 怎么样？」→ `financial-analysis`
- 「宁德时代和比亚迪财务对比」→ `peer-compare`
- 「600519 现在贵不贵？」→ `valuation`
- 「写一份宁德时代的五步法研报」→ `write-report`
