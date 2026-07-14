---
name: strategy-yaml-author
description: 通过对话生成 YAML 策略草稿，调用 save_strategy_draft；须人工 promote 后才能模拟/实盘。
---

# strategy-yaml-author

输出 YAML（id/name/when/then），并调用工具 `save_strategy_draft`。

约束：

- 默认 status=draft
- 不得声称已实盘运行
- 提醒用户到「策略管理」确认晋级
