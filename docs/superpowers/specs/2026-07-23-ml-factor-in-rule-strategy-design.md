# 规则策略支持 ML 因子（as_factor）

**日期：** 2026-07-23  
**状态：** 已实现  
**前置：** 规则策略构建器（`kind: factor_rules`）；登记模型「放入因子列表」

## 目标

让已放入因子列表的 ML 模型（`ml:{model_id}`）可在规则策略中与 TA 因子同等使用（比较 / 交叉），并支持回测与模拟盘 Runner；规则构建器下拉以 `因子名（说明）` 展示。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 模型范围 | 仅 `as_factor=true`（与因子页一致） |
| 条件能力 | 与现有 factor_rules 完全相同（比较 + 交叉，可与 TA / 其它 ML / 常数组合） |
| 技术方案 | 扩展 `factor_rules`（方案 A），不新建 `kind` |
| 列名 | 打分列名 = 因子名本身（如 `ml:my_lgb`），避免多模型撞 `ml_score` |
| 缺值 / 未放入 | 该条件为假，不中断回测 |
| 下拉文案 | `因子名（说明）`，说明取 API 的 `label`；含 ML |
| 性能 | 回测对完整 `history_df` 预打分；`on_bar` 切片自带列则 enrich 跳过 |

## 本期不做（已记入 `docs/TODO.md`，完成后提醒）

- 因子页「一键生成策略」
- 自动寻优阈值、仓位 / 持仓天数

## 规则示例

```yaml
id: rule_ml_score
name: ML打分阈值
kind: factor_rules
version: v1.0
buy:
  combine: all
  conditions:
    - { op: gt, left: { factor: "ml:my_lgb" }, right: { const: 0.6 } }
sell:
  combine: any
  conditions:
    - { op: lt, left: { factor: "ml:my_lgb" }, right: { const: 0.4 } }
    - { op: cross_down, left: { factor: "ml:my_lgb" }, right: { factor: SMA_20 } }
```

## 后端要点

1. **`factor_rules.py`**
   - `_primary_output("ml:…")` → 返回因子名字符串
   - `enrich_history_with_factors`：拆分 TA / `ml:`；TA 照旧；`ml:` 在列缺失且有 `db` 时经 `FactorService` 打分写入列
   - `eval_factor_rules`：从 `ctx["db"]` 取 Session（可选）
   - 导出 `attach_ml_factor_columns(history, names, db)` 供回测预计算

2. **`StrategyRegistry._yaml_on_bar`**
   - 注入 `ctx["db"] = self.db`，便于 enrich / 兜底打分

3. **`BacktestEngine.run`**
   - 若策略 YAML 含 `ml:`，在构建 cerebro 前对完整 `history_df` 调用 `attach_ml_factor_columns`

4. **`PaperStrategyRunner.run_once`**
   - 同样预打分或依赖 ctx.db + enrich（单次评估，预打分即可）

## 前端要点

- `StrategyRuleBuilder`：去掉排除 `category === "ml"` / `ml:` 的过滤
- 下拉：`label = name === label ? name : \`${name}（${label}）\``

## 测试要点

- 无 db / 未 as_factor 的 `ml:` → 条件假、无信号
- 有 as_factor 模型 + 阈值条件可触发买卖
- 列已存在时 enrich 不重复打分（可选）
- 前端：`factorOptions` 含 `ml:` 且文案带括号说明（单测解析/映射即可）

## 非目标（本期）

- Walk-Forward 内对 ML 重训
- 分钟线 ML 打分
- 修改训练特征管线
