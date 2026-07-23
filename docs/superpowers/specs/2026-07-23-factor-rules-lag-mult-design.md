# 规则操作数 lag + 比较 mult + VOLUME

**日期：** 2026-07-23  
**状态：** 已实现  
**入口：** 规则策略构建器操作数「滞后」；比较条件「右端×倍数」

## 目标

表达「今日量能 ≥ 昨日量能 × 2」等相对前 N 日、带倍数的比较；并注册 `VOLUME` 伪因子。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 形态 | 方案 A：操作数 `lag` + 比较右端 × `mult` |
| 判定 | `left` 与 `right × mult` 做 gt/gte/lt/lte/eq |
| 默认 | `lag=0`，`mult=1`；省略则与旧行为一致 |
| VOLUME | 伪因子，列 `volume`，与 CLOSE 等同注册 |
| 交叉 / near_pct | 支持操作数 `lag`；**不读 `mult`** |
| 不做 | 专用 `ge_mult` 算子、仅 VOLUME 模板、左端倍数 |

## YAML 示例

```yaml
- op: gte
  left: { factor: VOLUME }
  right: { factor: VOLUME, lag: 1 }
  mult: 2
```

常数右端也可乘倍数：`right: { const: 100 }, mult: 1.5` → 与 150 比较。

## 实现要点

- `_PRICE_FACTOR_COLS` / registry 增加 `VOLUME`
- `_resolve_operand`：因子可读 `lag`，从 enriched 按 bar 取 `i - lag`（需把 bar 下标传入，或在 `eval_condition_at` 路径解析）
- 比较分支：`rv_eff = rv * mult`（mult≤0 或无效 → 假）
- 前端：因子操作数滞后天数；比较算子显示 mult；dump/parse
- 单测：VOLUME 放量 2 倍；lag 越界假；无 mult 回归
