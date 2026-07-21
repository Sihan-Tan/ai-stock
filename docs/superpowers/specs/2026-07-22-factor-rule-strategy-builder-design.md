# 规则策略构建器（因子条件 → 策略）

**日期：** 2026-07-22  
**状态：** 已实现  
**入口：** 策略页「新建规则策略」（`/strategies/new/rules`）

## 目标

在策略页用可视化条件编辑器，把因子比较与交叉事件拼成可保存、可回测的规则策略（买卖各一套，AND/OR）。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 条件类型 | 数值比较 + 交叉（`cross_up` / `cross_down`） |
| 规则引擎 | 买卖各一套条件；`combine: all \| any` |
| 入口 | 仅策略页（不做因子页「拼成策略」） |
| 持久化 | 声明式 YAML，`kind: factor_rules`；旧 `sma_fast/sma_slow` 兼容 |
| 冲突 | 同 bar 买卖皆满足时 **卖优先** |
| 一期不做 | ML 登记模型绑定、仓位/持仓天数、流程图、纸交易专属参数 |

## 规则 schema（草案）

```yaml
id: rule_rsi_oversold
name: RSI超卖+均线金叉
kind: factor_rules
version: v1.0
buy:
  combine: all
  conditions:
    - { op: lt, left: { factor: RSI_14 }, right: { const: 30 } }
    - { op: cross_up, left: { factor: SMA_5 }, right: { factor: SMA_20 } }
sell:
  combine: any
  conditions:
    - { op: gt, left: { factor: RSI_14 }, right: { const: 70 } }
    - { op: cross_down, left: { factor: SMA_5 }, right: { factor: SMA_20 } }
```

**算子：** `gt` / `gte` / `lt` / `lte` / `eq` / `cross_up` / `cross_down`  
**操作数：** `{ factor: <因子目录名> }` 或 `{ const: <number> }`

## 后端要点

- 扩展 `_yaml_on_bar`：识别 `kind: factor_rules` → 通用求值器
- 用回测注入的 `history` / 指标列计算所需因子；交叉用当日与前一日
- 未知因子名：该条件为假，不中断回测

## 前端要点

- 买卖两栏；条件行：左因子 | 算子 | 右（因子或常数）
- 因子下拉来自 `GET /api/factors`（一期 TA；不含 ML 登记模型）
- 保存走现有策略 API，列表可回测

## 技术方案

声明式规则 + 求值器（优于生成 Python 或继续扩死板 `sma_*` YAML）。

## 非目标（一期）

- 因子页出口、ML `model_id` 绑定、复杂仓位管理
