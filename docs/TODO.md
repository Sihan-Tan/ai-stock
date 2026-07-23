# 项目待办（下一期）

## 策略

- [x] **规则策略构建器（因子条件 → 策略）**  
  - 设计：`docs/superpowers/specs/2026-07-22-factor-rule-strategy-builder-design.md`  
  - 计划：`docs/superpowers/plans/2026-07-22-factor-rule-strategy-builder.md`  
  - 入口：策略页「新建规则策略」→ `/strategies/new/rules`

- [x] **规则策略支持 ML 因子（as_factor）**  
  - 设计：`docs/superpowers/specs/2026-07-23-ml-factor-in-rule-strategy-design.md`  
  - 计划：`docs/superpowers/plans/2026-07-23-ml-factor-in-rule-strategy.md`  
  - 范围：`ml:` 进 factor_rules；下拉 `名（说明）`；回测预打分

### 本期待办完成后提醒（暂不做）

- [ ] **因子页「一键生成策略」** — 从已放入的 ML/TA 因子一键跳到规则策略并预填条件  
- [ ] **自动寻优阈值、仓位/持仓天数** — 网格/搜索买卖阈值与简易仓位、最长持仓，写入策略参数  

## 备注

完成一项后请勾选，并视情况补实现计划到 `docs/superpowers/plans/`。  
完成「规则策略支持 ML 因子」后，请主动提醒用户推进上方「暂不做」两项。
