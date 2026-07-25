# 项目待办

## 文档同步（2026-07-25）

已与代码对齐的规格（状态 → 已实现 / 行为已更新）：

- [x] 投研精选（含价格计划、飞书全量、分批加速）— `specs/2026-07-25-research-refine-design.md`
- [x] 飞书告警开关（含托管类别 `research`）— `specs/2026-07-25-feishu-alert-switch-design.md`
- [x] 分时开盘集合竞价 — `specs/2026-07-18-intraday-auction-design.md`
- [x] 登记模型删除与放入因子列表 — `specs/2026-07-21-ml-model-factor-list-design.md`

说明：部分历史 plan 文件顶部 checkbox 可能仍为草稿痕迹；以对应 **spec 状态** 为准。

## 策略（已完成）

- [x] **规则策略构建器（因子条件 → 策略）**  
  - 设计：`docs/superpowers/specs/2026-07-22-factor-rule-strategy-builder-design.md`  
  - 计划：`docs/superpowers/plans/2026-07-22-factor-rule-strategy-builder.md`  
  - 入口：策略页「新建规则策略」→ `/strategies/new/rules`

- [x] **规则策略支持 ML 因子（as_factor）**  
  - 设计：`docs/superpowers/specs/2026-07-23-ml-factor-in-rule-strategy-design.md`  
  - 计划：`docs/superpowers/plans/2026-07-23-ml-factor-in-rule-strategy.md`  
  - 范围：`ml:` 进 factor_rules；下拉 `名（说明）`；回测预打分

## 下一期功能（暂未做）

- [ ] **因子页「一键生成策略」** — 从已放入的 ML/TA 因子一键跳到规则策略并预填条件  
- [ ] **自动寻优阈值、仓位/持仓天数** — 网格/搜索买卖阈值与简易仓位、最长持仓，写入策略参数  

## 备注

完成一项后请勾选，并视情况补实现计划到 `docs/superpowers/plans/`。  
完成「规则策略支持 ML 因子」后，请主动提醒用户推进上方「下一期」两项。
