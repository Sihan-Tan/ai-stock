# 投研精选图片表格推送 + 持仓建议附名称

> 状态：待实现  
> 日期：2026-08-07

## 目标

早晚盘自动/手动触发的**投研精选**飞书推送，改为 **Pillow 生成表格 PNG → 飞书开放平台上传 → Webhook 发图片**；**持仓建议**推送行在代码后附带股票名称。

## 决策摘要

| 项 | 选择 |
|----|------|
| 发图方式 | A：Pillow PNG + `app_id`/`app_secret` 上传 `image_key` |
| 表格列 | B：排名、代码、名称、评分、置信度、买入、目标、止损、理由 |
| 理由 | 单元格内换行，最多 3 行，超出截断 |
| 图文搭配 | 只发图片；标题画进图顶 |
| 失败策略 | 无凭证/上传失败 → 回退现有纯文本 |
| 持仓建议 | `{代码} {名称} {动作}｜{理由}` |

## §1 凭证与飞书图片通道

### 配置

新增（可空）：

- `feishu_app_id`
- `feishu_app_secret`

保留：`feishu_webhook_url`、`feishu_sign_secret`、`feishu_alert_enabled`、`feishu_alert_categories`。

### `FeishuWebhookChannel`

- 新增 `send_image(title, image_bytes, category, dedupe_key, *, force=False)`：
  1. 用 app 凭证获取 `tenant_access_token`
  2. 调用飞书上传图片接口得到 `image_key`
  3. Webhook 发送 `msg_type: image`（若配置了签名则附带）
  4. 告警表 `body` 写入短摘要（如 `[image] {title}`），便于列表查看
- 现有 `send()` 文本路径不变
- 缺凭证、上传失败、POST 失败时返回可识别失败状态，由调用方回退文本

### 非目标

- 不把 morning/closing 选股主文改成图片
- 不做飞书互动卡片 / post 富文本表

## §2 投研精选表格图

### 模块

建议：`packages/ai/desk_ai/research_table_image.py`（纯函数，便于单测）

### 画面

- 顶栏标题：`投研精选·{source}  {asof}  共 N 只`
- 列：排名 | 代码 | 名称 | 评分 | 置信度 | 买入 | 目标 | 止损 | 理由
- 价格：`low–high`（止损单值），保留 2 位小数
- 理由：最多 3 行，超出截断加省略号
- 深色风格；中文字体优先系统字体（如微软雅黑），缺字回退

### 输出

PNG `bytes`。行数与精选结果一致（通常 ≤ top_n / max_candidates 上限）。

### 依赖

Pillow，写入对应 package 依赖声明。

## §3 接线

### 投研精选（`desk_ai.refine._maybe_feishu`）

1. `picks` 非空 → 渲染 PNG → `send_image`
2. 成功则不再发送长文本正文
3. 失败则 `format_research_feishu_body` + 原 `send`
4. `category=research`、`dedupe_key` 规则不变

### 持仓建议（`append_advice_section`）

- 行：`{symbol} {name} {action}｜{reason}`（名称为空则不留多余空格）
- 名称：`quotes_snapshot.name` → `get_security_meta` → `""`
- 拼段前批量解析；预置 `section`（无持仓等）不改

### 设置页（一期建议包含）

- 增加飞书 App ID / App Secret 配置（密钥脱敏）

## 测试

1. 表格图：列齐全；理由截断 ≤3 行；空 picks 行为明确（不推或调用方跳过）
2. alert：mock 上传成功走 image；失败可回退
3. format：有名称 / 无名称两种持仓行文案

## 手工验收

- 配置 app 凭证后触发精选：飞书收到表格图，顶栏标题正确
- 去掉凭证或故意上传失败：仍能收到旧版文本精选
- 早晚盘选股消息中持仓建议行为 `代码 名称 动作｜理由`

## 非目标

- 持仓建议整段改图片
- 选股主列表改图片
- 飞书侧表格消息类型（非 image）
