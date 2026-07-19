# 风控与边界硬规则（v1）

## 交易

1. 默认 `TRADE_MODE=paper`；实盘需显式 ARM（设置页或 `RISK_ARMED=1` / `POST /api/broker/risk`）。
2. Kill Switch 打开时拒绝一切 live 单。
3. 实盘受单笔/单日名义限额与标的白名单约束。
4. AI / nanobot **禁止**注册实盘下单或解除 Kill Switch 的工具。
5. 投研财务类工具（`get_financials` / `peer_compare` / `get_valuation` 等）**只读**，不得触发下单或修改风控状态。

## 引擎边界

| 能力 | 唯一实现 |
| --- | --- |
| 回测 | `backtrader`（`BacktraderRunner`） |
| 技术指标 | 仅经 `packages/indicators`（无 TA-Lib C 库时 pandas 回退） |
| ML | 仅 LightGBM / XGBoost（`ModelBackend`） |
| 投研对话 | nanobot 适配层 + `skills/` |

## 数据

- 关系库为行情/持仓/策略等真相源（默认 PostgreSQL，可切 MySQL；本地演示可用 SQLite）。
- Agent 策略草稿默认 `draft`，`promote` 后才可进研究/模拟；禁止对话直通实盘。

## 告警

- 默认通道：飞书 Webhook；未配置 URL 时仅落库 `alerts`（`logged_only`）。
