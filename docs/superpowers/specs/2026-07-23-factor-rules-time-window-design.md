# 规则条件跨日窗口（sequence / within）

**日期：** 2026-07-23  
**状态：** 已实现  
**入口：** 规则策略构建器「组合方式」+「间隔/窗口（交易日）」

## 目标

让 `factor_rules` 的买入/卖出条件不必在同一根 K 线同时成立：支持**有序间隔**与**近 N 日均曾成立**；保留现有同日 `all` / `any`。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 范围 | A + B：`combine: sequence` 与 `combine: within` |
| 窗口字段 | 侧级 `within_bars`（非条件级）；未写默认 **5** |
| 单位 | 交易日（history 行数），非自然日 |
| 同日 | `sequence` 允许相邻两步落在同一根（间隔 0） |
| 触发日 | `sequence`：最后一步必须落在**当日**才发信号 |
| `within` 触发 | 近窗内每条条件至少一日为真即触发；**允许同日**（各条件可在同一根成立）；也可分散在窗内不同日；状态类条件可连续多日为真（与同日 `all` 一致；仓位由回测/纸交易处理） |
| 买卖 | buy / sell 均支持 |
| 兼容 | 现有 `all` / `any` 忽略 `within_bars`，行为不变 |
| 不做（本期） | 显式状态机持久化、条件级各自窗口、`within` 再套 `any`、自然日日历 |

## 语义

### `combine: sequence`（有序间隔）

条件按列表顺序编号 `0..k-1`。侧触发当且仅当存在下标序列 `t0 ≤ t1 ≤ … ≤ t_{k-1}`，满足：

1. 第 `j` 条条件在 bar `t_j` 上为真（求值方式与现网一致：比较 / 交叉 / `near_pct`；交叉用 `t_j` 与 `t_j-1`）；
2. 对 `j ≥ 1`：`0 ≤ t_j - t_{j-1} ≤ within_bars`；
3. `t_{k-1}` 等于当日 bar 下标（链条在今日收尾）。

单条件时退化为：当日该条件为真（与 `all` 单条件等价）。

### `combine: within`（近 N 日均曾成立）

与 `sequence` 共用距离定义：bar 下标差 `today_i - i ≤ within_bars` 且 `i ≤ today_i`（即含今日在内、往回最多 N 根；下界截断到 0，交叉条件在 `i < 1` 视为假）。

侧触发当且仅当：**每一条**条件在该窗内至少有一个 bar 为真。条件之间**无先后**要求；**允许多条条件落在同一根 K 线**（同日满足也算通过）。

### `all` / `any`（不变）

仅用当日（及交叉所需前一日）求值；不读 `within_bars`。

## YAML 示例

```yaml
kind: factor_rules
buy:
  combine: sequence
  within_bars: 5
  conditions:
    - op: cross_up
      left: { factor: SMA_5 }
      right: { factor: SMA_20 }
    - op: near_pct
      left: { factor: CLOSE }
      right: { factor: SMA_20 }
      pct: 3
sell:
  combine: within
  within_bars: 10
  conditions:
    - op: lt
      left: { factor: RSI_14 }
      right: { const: 30 }
    - op: cross_down
      left: { factor: SMA_5 }
      right: { factor: SMA_20 }
```

## 实现要点

### 后端 `desk_strategy.factor_rules`

- 抽取「在 bar `i` 上求单条条件」：`(cond, enriched, i) -> bool`（`i < 1` 且为交叉 → 假）。
- `_side_triggered(block, enriched, today_i)`：按 `combine` 分发 `all` / `any` / `sequence` / `within`。
- `eval_factor_rules`：enrich 后传入完整 `enriched` 与 `today_i = len-1`，不再只传 `cur`/`prev` 做侧组合（单条求值仍可用 cur/prev）。
- `within_bars`：解析为非负整数；非法/缺失 → 默认 5；`sequence`/`within` 在 `within_bars < 0` 时视为不触发。
- 单测：同日两步 sequence；跨 3 日 sequence 成功/超窗失败；within 无序成功；最后一步非今日 sequence 不触发；`all` 回归。

### 前端 `StrategyRuleBuilder`

- 组合方式选项增加：`有序间隔` → `sequence`，`近N日均曾成立` → `within`。
- 当 combine ∈ {sequence, within} 时显示「间隔/窗口（交易日）」数字输入，绑定 `within_bars`。
- `dumpFactorRulesYaml` / `parseFactorRulesYaml` 读写侧级 `within_bars`。
- 轻量 vitest：dump/parse 含 `sequence` + `within_bars`。

## 验收

1. 规则页可选两种新组合并保存 YAML。
2. 回测：sequence「金叉后 N 日内 near_pct」可成交；超窗无买。
3. within：两条件不同日成立且都在窗内可触发。
4. 旧策略 `combine: all` 行为与改前一致。
