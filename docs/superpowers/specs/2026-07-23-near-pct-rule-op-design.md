# 规则算子 near_pct（价格贴近均线）

**日期：** 2026-07-23  
**状态：** 已实现  
**入口：** 规则策略构建器算子「贴近(±%)」

## 目标

在 `factor_rules` 中表达「价格相对某因子（通常为均线）落在 ±N% 内」，例如收盘价在 SMA_20 ±3%。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 形态 | 方案 B：左=价格因子，右=参考因子，`pct`=±百分比 |
| 公式 | `\|left / right − 1\| × 100 ≤ pct`；`right=0`/缺值 → 假 |
| 价格侧 | 伪因子 `CLOSE`（取 `history.close`）；本期不做开高低 |
| 默认 pct | 未写时按 `3` |
| 不做 | 因子页贴均线专用图、OPEN/HIGH/LOW |

## YAML 示例

```yaml
- op: near_pct
  left: { factor: CLOSE }
  right: { factor: SMA_20 }
  pct: 3
```

## 实现要点

- `factor_rules`：注册 `near_pct`；解析 `CLOSE` → 列 `close`；enrich 跳过对 CLOSE 的 TA 计算
- 注册表 / `/api/factors`：暴露 `CLOSE`（category=price）
- 规则构建器：算子「贴近(±%)」+ ±% 输入；dump/parse 读写 `pct`
