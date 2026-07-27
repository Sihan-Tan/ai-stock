# 项目待办

## 进行中

- [x] **投研形态手册（知识库预检索）** — skill `pattern-playbook`；启用时预检索笔记对照形态/走势  
  - 设计：`docs/superpowers/specs/2026-07-25-pattern-playbook-design.md`

## 后续（暂不做）

- [ ] **知识库纯本地向量** — `sentence-transformers` 离线 embedding / 索引（不依赖云端 API）  
  - 前置：知识库工作台落地后再做

## 已完成（策略）

- [x] **早盘/尾盘选股附带持仓建议** — `desk_positions_advice`；与选股同一条飞书推送  
  - 设计：`docs/superpowers/specs/2026-07-27-positions-advice-design.md`
- [x] **知识库工作台 + PDF + 可切换检索**  
  - 设计：`docs/superpowers/specs/2026-07-25-knowledge-workbench-design.md`  
  - 范围：CRUD、PDF/md/txt 上传、keyword/vector/hybrid（云端 embedding）
- [x] 规则策略构建器 — `specs/2026-07-22-factor-rule-strategy-builder-design.md`
- [x] 规则策略支持 ML 因子 — `specs/2026-07-23-ml-factor-in-rule-strategy-design.md`
- [x] 因子一键生成 + 完整净值寻优 — `specs/2026-07-25-factor-rule-optimize-design.md`

## 文档同步（摘录）

- [x] 投研精选 / 飞书开关 / 分时竞价 / ML 因子列表等规格已与代码对齐（见 `docs/superpowers/specs/`）

## 备注

完成一项后请勾选，并视情况补实现计划到 `docs/superpowers/plans/`。
