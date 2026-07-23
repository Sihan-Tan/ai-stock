# 规则 sequence 分阶段（组内同日 + 段间间隔）

**日期：** 2026-07-23  
**状态：** 已实现  
**入口：** 规则构建器「有序间隔」→ 阶段列表

## 目标

表达「A、B 同一天满足后，再在 ≤N 个交易日内 C 满足」：阶段内同日组合，阶段间可配置间隔。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 形态 | 方案 A：`combine: sequence` + `stages[]` |
| 阶段内 | `all` / `any`（同日） |
| 段间间隔 | 写在**后一段**的 `within_bars`（相对前一段完成日）；`0 ≤ Δ ≤ within_bars` |
| 触发 | 最后阶段落在**当日** |
| 兼容 | 无 `stages` 时：扁平 `conditions` 每条各成一段，段间用侧级 `within_bars` |
| 默认 | 后段未写间隔 → 侧级 `within_bars` 或 5 |
| 不做 | 阶段内再跨日、`min_bars` 下限、无限嵌套 |

## YAML 示例

```yaml
buy:
  combine: sequence
  within_bars: 5
  stages:
    - combine: all
      conditions:
        - { op: gt, left: { factor: SMA_5 }, right: { const: 0 } }
        - { op: gt, left: { factor: VOLUME }, right: { factor: VOLUME, lag: 1 }, mult: 2 }
    - combine: all
      within_bars: 5
      conditions:
        - { op: near_pct, left: { factor: CLOSE }, right: { factor: SMA_20 }, pct: 3 }
```

## 实现要点

- `collect_factor_names` 遍历 `stages`
- `_sequence_triggered` 按阶段回溯（存在性）
- 前端 sequence 下编辑阶段；dump/parse `stages`
- 单测：两阶段 A∧B 后 C；兼容扁平 sequence
