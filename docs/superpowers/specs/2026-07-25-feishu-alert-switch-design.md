# 飞书告警开关设计

**日期：** 2026-07-25  
**状态：** 已实现  
**入口：** 设置 → 飞书告警

## 目标

为飞书告警增加总开关与按类别开关：关闭后自动告警不发 Webhook；设置页「测试推送」不受总开关限制，便于验证通道。

## 非目标

- 不改变 Webhook / 签名密钥配置方式
- 不做按策略、按标的的细粒度静音
- 不引入独立告警策略表

## 行为矩阵

| 场景 | Webhook | 落库 status |
|------|---------|-------------|
| 总开关关（非测试） | 不发 | `disabled` |
| 总开关开、该类别关 | 不发 | `disabled` |
| 总开关开、该类别开 | 与现网一致 | `sent` / `logged_only` / `failed:*` / `deduped` |
| 测试推送 | 始终可走发送路径 | 与现网一致 |

默认：

- `feishu_alert_enabled = true`
- 允许类别：`morning`, `closing`, `paper`（**不含** `risk`）
- 未知类别：总开关开时视为允许（避免新来源被误杀）

## 配置

写入 `.env`，经现有 `settings` / `settings_store` 读写：

| 字段 | 环境变量 | 类型 | 默认 |
|------|----------|------|------|
| `feishu_alert_enabled` | `FEISHU_ALERT_ENABLED` | bool | `true` |
| `feishu_alert_categories` | `FEISHU_ALERT_CATEGORIES` | 逗号分隔字符串 | `morning,closing,paper` |

保存设置后热更新，与其它设置相同。

## 拦截点

唯一拦截：`FeishuWebhookChannel.send`。

顺序建议：

1. 去重（保持现有 5 分钟逻辑）
2. 若非测试推送，且（总开关关 **或** 类别不在允许列表）→ 落库 `disabled`，返回，不 POST
3. 否则走现有发送 / `logged_only` 逻辑

测试推送判定（满足其一即可）：

- 调用方传入 `force=True`
- 或 `category` ∈ `{test, manual}`

设置页与告警页的测试按钮应使用 `force=True`（或 `category=test`），保证总开关关闭时仍可测。

## UI

「设置 → 飞书告警」在 Webhook / 签名下方增加：

1. 「启用飞书告警」总开关
2. 类别开关（勾选写入 `feishu_alert_categories`）：
   - 早盘 `morning`
   - 尾盘 `closing`
   - 纸交易 `paper`
   - 风控 `risk`
3. 说明文案：关闭总开关后自动告警静音；测试推送仍可用

## 调用方改动

| 来源 | category | 备注 |
|------|----------|------|
| 早盘 | `morning` | 无改，走开关 |
| 尾盘 | `closing` | 无改 |
| 纸交易成交等 | `paper` | 无改 |
| 风控 | `risk` | 默认静音 |
| 测试推送 | `test` + `force` | 绕过开关 |

## 验收

1. 关总开关 → 早盘/尾盘/纸交易 `send` 返回 `disabled`，无 HTTP
2. 只关 `morning` → 早盘静音，尾盘仍可发
3. 默认配置下 `risk` 静音
4. 总开关关时测试推送仍可 `sent` 或 `logged_only`
5. 单测覆盖总开关、类别、`force` 三条路径

## 实现要点（实现阶段）

- `packages/common`：Settings + settings_store 映射
- `packages/alert`：`send(..., force=False)` + 允许列表解析
- `apps/api` settings 路由透出字段
- `apps/web` Settings 飞书 Tab UI
- `tests/test_feishu_alert.py` 增补开关用例
