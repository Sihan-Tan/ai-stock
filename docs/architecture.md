# 刻度 Desk · 架构说明

## 边界

- **关系库**为行情/持仓/策略等真相源（默认 PostgreSQL，可切 MySQL；演示/测试可用 SQLite）
- **backtrader** 唯一回测内核
- **TA-Lib** 经 `desk_indicators`（无库时 pandas 回退）
- **LightGBM / XGBoost** 经 `desk_ml.ModelBackend` 切换
- **nanobot** 仅服务投研对话（`desk_ai` + `skills/`），禁止实盘下单工具
- **飞书** 为默认告警通道
- 硬规则详见 [`docs/hard-rules.md`](hard-rules.md)

## 包一览

| 包 | 职责 |
| --- | --- |
| `desk_common` | Settings、符号规范化、Pydantic 合约 |
| `desk_db` | SQLAlchemy 模型与会话 |
| `desk_market` / `desk_calendar` | 行情、自选、日历、停牌 |
| `desk_sentiment` / `desk_lhb` | 打板情绪、龙虎榜 |
| `desk_indicators` / `desk_factor` / `desk_ml` | 指标、因子、双引擎 ML |
| `desk_strategy` / `desk_backtest` | 三通道策略、backtrader |
| `desk_broker` / `desk_alert` | Paper / Mock·QMT / RiskGate、飞书 |
| `desk_ai` / `desk_morning_brief` / `desk_review` / `desk_knowledge` | 投研、晨会、复盘、知识库 |
| `apps/api` | FastAPI |
| `apps/web` | React + Vite |
| `skills/` | nanobot 自建 Skill |

## 关键数据流

```text
行情源(AkShare/QMT) → DB → 因子/指标 → 策略 Signal
                                    ↘ backtrader 回测 → DB
信号 → BrokerGateway → PaperBroker / RiskGate+QmtBroker
投研对话 → desk_ai(nanobot适配) → 只读工具 + save_strategy_draft
```

## Mock CI

本地：`pwsh scripts/smoke_mock.ps1`  
或：`DATABASE_URL=sqlite:///:memory: pytest -q`  
GitHub Actions：`.github/workflows/ci.yml`（SQLite 内存库 + pytest + 前端 build；不连真实 QMT/飞书）。

## 启动

```bash
docker compose up -d postgres
cp .env.example .env
pip install -e ".[dev]"
# 开发可用 SQLite：
# set DATABASE_URL=sqlite:///./data/desk.db
cd apps/api && uvicorn app.main:app --reload --app-dir .
cd apps/web && npm install && npm run dev
```
