---
name: financial-analysis
description: 单股财务趋势分析；调用 get_financials 解读毛利率、ROE、负债与现金流。
---

# financial-analysis

针对单只股票做基本面财务解读，只读、不给出买卖建议。

## 工具

- `get_financials`：输入 `symbol`（必填），可选 `years`（默认 5）

## 工作流

1. 调用 `get_financials` 获取标准化指标序列与 `source`。
2. 若返回含 `error` 或无有效 `metrics`，说明数据缺失原因，停止编造。
3. 有数据时按维度解读：
   - **盈利能力**：毛利率、净利率、ROE、ROA 趋势
   - **成长**：营收、净利润同比增速
   - **负债与偿债**：资产负债率、有息负债、流动比率
   - **现金流**：经营现金流与净利润匹配度、自由现金流
4. 结论标注数据来源（如 `source: qmt`），区分事实与推断。

## 约束

- 禁止 exec 脚本或外部 Python 路径；仅使用 Desk 工具。
- 禁止下单、禁止修改交易开关。

## 示例问法

- 「600519 近五年财务怎么样？」
- 「比亚迪 ROE 和负债率趋势」
