---
name: write-report
description: 五步法深度投研报告（业务/壁垒/预期差/风险/估值）；组合财务工具、网页搜索与知识库检索成文。
---

# write-report

按五步法撰写结构化投研报告，数字来自工具，定性部分需标注推断依据。

## 工具

- `get_financials`：财务趋势与关键指标
- `get_valuation`：估值与分位（可带 `peers`）
- `web_search`：行业动态、竞争格局、政策（未配置 Key 时可能返回 error，可跳过并说明）
- `search_knowledge`：检索已有研报/笔记补充上下文
- `save_research_note`：可选，用户要求保存时将成文写入知识库

## 五步法结构

1. **业务**：主营业务、收入结构、行业地位（`web_search` + `search_knowledge` 辅助）
2. **壁垒**：护城河、竞争格局、差异化（结合工具事实与检索，标注推断）
3. **预期差**：市场共识 vs 你的判断，需说明依据
4. **风险**：行业、政策、财务、竞争等风险清单
5. **估值**：`get_valuation` 结果 + 相对同行；无数据则不写具体倍数

## 建议调用顺序

1. `get_financials`（symbol, years）
2. `get_valuation`（symbol, 可选 peers）
3. `web_search`（行业/公司关键词；失败则注明并继续）
4. `search_knowledge`（相关主题检索）
5. 按五步法成文；用户明确要求保存时调用 `save_research_note`（title, body, symbols）

## 约束

- 禁止 exec 脚本或 `python skills/.../scripts/*.py` 路径；仅使用上列 Desk 工具。
- 财务与估值数字必须来自工具；禁止编造 PE/ROE 等。
- 禁止下单、禁止修改风控；不自动调用 `save_strategy_draft`。

## 示例问法

- 「写一份宁德时代的五步法研报」
- 「分析茅台的护城河、预期差和估值，保存到笔记」
