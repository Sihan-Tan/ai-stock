# 飞书告警完成（通道加固 + 纸交易接入）

**日期：** 2026-07-25  
**状态：** 已实现  
**入口：** 设置 → 飞书告警「测试推送」；纸交易 Runner 成交/拒绝自动推送

## 目标

打磨飞书 Webhook 通道可靠性，并将模拟盘关键成交/拒绝接到告警，形成可用闭环。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 范围 | 方案 A：通道加固 + 纸交易路径 |
| 成功判定 | HTTP 2xx 且响应 `code==0`（无 JSON/`code` 字段时仅看 HTTP） |
| 测试推送 | 设置页飞书 Tab 调用既有 `POST /api/alerts/send` |
| 成交告警 | `PaperStrategyRunner` 下单成功 → `category=paper` |
| 拒绝告警 | 闸门挡住或 `place_order` 失败 → `category=risk` |
| 去重 | 成交 `paper:{sid}:{sym}:{side}:{date}`；拒绝 `reject:{sid}:{sym}:{side}:{date}` |
| 不做 | 情绪/龙虎榜/停牌全量规则、富文本卡片、信号未成交也推送 |

## 实现要点

- `FeishuWebhookChannel._post`：解析响应 body，业务失败 → `failed`
- 设置页：测试推送按钮 + 结果提示
- `paper_runner.run_once`：下单循环内发送告警（有 db Session）
- 单测：Mock httpx 业务 code≠0；Runner 成功/拒绝触发 send（可 Mock channel）
