# 刻度 Desk · 个人 AI 量化工作台

本地优先（Windows + miniQMT）的个人 AI 量化交易系统。v1 产品范围已冻结，见 [`docs/v1.md`](docs/v1.md)；风控边界见 [`docs/hard-rules.md`](docs/hard-rules.md)。

---

## 已有功能

按 Web 导航与后端能力归纳（均可在本地一键启动后使用；部分能力依赖行情落库 / LLM Key / QMT）。

| 模块 | 路由 / 入口 | 能力概要 |
| --- | --- | --- |
| 实盘监控（模拟盘） | `/monitor` | 纸交易账户、持仓、下单；Paper Runner 手动/定时扫自选 |
| 行情自选 | `/watchlist` | 自选股、报价、跳转个股详情 |
| 个股详情 | `/stock/:symbol` | K 线（含竞价段）、报价、板块/资金流/技术面等 |
| 打板情绪 | `/sentiment` | 涨停池等情绪日表同步与展示 |
| 龙虎榜 | `/lhb` | 龙虎榜明细同步与复盘关联 |
| 交易日历 | `/calendar` | 交易日 / 停牌等事件 |
| 策略 | `/strategies` | Python 注册 / YAML / Agent 草稿；生命周期与 KPI |
| 回测 | `/backtest` | backtrader 日/分钟回测，报告落库 |
| 因子 / ML | `/factors` | 因子与 LightGBM / XGBoost 训练推理（可切换引擎） |
| 告警 | `/alerts` | 飞书 Webhook 等告警记录 |
| 投研 | `/ai` | 多轮流式对话、Skills 勾选/详情、Markdown/JSON 富文本 |
| 晨会 | `/morning` | 盘前简报、竞价强势池 |
| 行情同步 | `/market-sync` | 日线/分钟/标的列表等同步任务与任务状态 |
| 复盘 | `/review` | 复盘笔记 |
| 知识库 | `/knowledge` | 研报/笔记上传、切片、检索（供投研 RAG） |
| 设置 | `/settings` | 交易模式、LLM、QMT、Paper Runner、告警等 |

**投研 Skills（`skills/`）**：`investment-research`、`financial-analysis`、`peer-compare`、`valuation`、`write-report`、`serenity-report`、`desk-readonly`、`knowledge-rag`、`strategy-yaml-author`、`auction-strong-pick` 等。工具只读（财务/估值/搜索/知识库）；禁止对话下单。

**数据与基础设施**：PostgreSQL（默认）/ MySQL / SQLite；SQLAlchemy + `create_all` 建表；行情日 K/分钟 K、财务快照缓存、核心行情 CSV 导出导入。

---

## 待完善功能

下列为已知缺口或体验体验，**不改变 v1 冻结范围**；按优先级可持续迭代。

| 方向 | 现状 | 建议完善 |
| --- | --- | --- |
| 真 QMT 实盘 | 默认 `QMT_FORCE_MOCK=1`，无柜台或未配齐时走 Mock | 接真 miniQMT 只读→下单；审批队列与自动成交双开关生产验证 |
| Paper 闭环 | Runner / 成本 / 生命周期闸门已有基础 | 定时 Runner 默认关；Walk-Forward KPI、晋升闸门与监控页状态可再打磨 |
| 投研 serenity-report | 方法论可勾选加载 | 附属 references 不会自动注入上下文；无本地脚本执行；深度信源依赖 `web_search`（Tavily） |
| 投研工具面 | 财务 + 估值 + 搜索 + 知识库 | 公告/浏览器类工具、更稳的多源证据链 |
| 部署形态 | 本地双进程开发为主 | 无官方 Docker 全栈镜像；生产需自备进程守护、备份、HTTPS 反代 |
| 文档与 CI | README + Mock smoke | 操作手册细化、迁移/备份流程、CI 门禁统一（含前端 `tsc` 既有问题清理） |
| 其它 | 港股/期货等 | v1 明确不做，需另开变更 |

更细的对照与阶段规划可参考：`docs/superpowers/plans/2026-07-19-research-to-paper-loop.md`、`docs/v1.md`。

---

## 启动与部署

### 环境要求

- **OS**：Windows 优先（适配 miniQMT）；Linux/macOS 可跑 API + Web（无 QMT 真柜台）
- **Python** 3.11+
- **Node.js** 18+（前端 Vite）
- **数据库**（三选一）  
  - PostgreSQL 16+（推荐，`docker compose` 已提供）  
  - MySQL 8+  
  - SQLite（本地演示 / 无 Docker）

### 1. 克隆与依赖

```powershell
# 仓库根目录
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
# 可选：pip install TA-Lib   # Windows 需匹配 Python 的 wheel

cd apps/web
npm install
cd ../..
```

### 2. 配置与数据库

```powershell
copy .env.example .env
# 编辑 .env：DATABASE_URL、LLM_*、飞书、QMT 等
```

**PostgreSQL（推荐）**

```powershell
docker compose up -d postgres_stock
# .env 中保持类似：
# DATABASE_URL=postgresql+psycopg://desk:desk@localhost:5432/desk
```

**SQLite（无 Docker）**

```powershell
$env:DATABASE_URL="sqlite:///./data/desk.db"
# 或写入 .env；一键脚本在缺少 .env 时也会默认写 SQLite
```

**MySQL**：`docker compose --profile mysql up -d mysql_stock`，并将 `DATABASE_URL` 改为 `mysql+pymysql://desk:desk@localhost:3306/desk`。

首次连库时应用会尽量 `create_all` 建表。也可用 `scripts/reset_db_schema.py`（会清空数据，慎用）配合 Alembic 场景。

### 3. 本地一键启动（开发推荐）

```powershell
.\scripts\dev.ps1
# 或
python scripts/dev.py
# 或
npm run dev
```

行为：

- 同时启动 **FastAPI** `http://127.0.0.1:8000` 与 **Vite** `http://127.0.0.1:5173`
- 前端将 `/api`、`/health` 代理到后台
- **Ctrl+C** 结束两个进程
- 启动前检查 Python 包与 `apps/web/node_modules`

| 地址 | 用途 |
| --- | --- |
| <http://127.0.0.1:5173/> | 前端工作台 |
| <http://127.0.0.1:8000/health> | 健康检查 |
| <http://127.0.0.1:8000/docs> | OpenAPI |

### 4. 分开启动（可选）

```powershell
# API（仓库根目录，已激活 venv）
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir apps/api

# 前端
cd apps/web
npm run dev
```

### 5. 部署建议（个人本机 / 小服务器）

本项目定位是**本地交易工作台**，不是开箱即用的 SaaS。自行部署时建议：

1. 使用 PostgreSQL 持久卷；定期备份库与 `data/market` CSV（见下节）
2. API / Web 用进程管理（如 NSSM、Task Scheduler、systemd）托管，勿长期挂 `--reload`
3. 生产关闭调试热重载；`TRADE_MODE=paper` 直至风控与 QMT 就绪
4. 实盘：`QMT_FORCE_MOCK=0`，配置 `QMT_USERDATA_PATH` / 账号，并满足 ARM + 白名单 + Kill Switch（见硬规则）
5. 反向代理（可选）：将 `5173`/`8000` 收到同一域名；注意 WebSocket/SSE（投研流式）超时
6. 密钥只放 `.env` 或系统环境变量，勿提交仓库

### 6. 行情灌库与同步

- **日常**：Web「行情同步」或相关 jobs / API 拉取写入  
- **备份迁移**：见下方「行情数据导出 / 导入」  
- 情绪 / 龙虎榜等同理在对应页面触发同步  

### 7. 测试

```powershell
$env:DATABASE_URL="sqlite:///:memory:"
pytest -q
# 可选 Mock CI
# pwsh scripts/smoke_mock.ps1
```

---

## 行情数据导出 / 导入

备份或迁移**核心行情表**：

| 表 | 说明 |
| --- | --- |
| `bars_daily` | 日 K |
| `bars_minute` | 分钟 K |
| `quotes_snapshot` | 行情快照 |
| `security_meta` | 标的元数据 |
| `trade_calendar` | 交易日历 |

输出目录默认 `data/market/`（CSV + `manifest.json`）。该目录在 `.gitignore` 中（体积可能很大），仓库仅保留 `data/market/.gitkeep`。

```powershell
# 导出（默认读 .env 的 DATABASE_URL）
python scripts/export_market_data.py
python scripts/export_market_data.py --url "sqlite:///./data/desk.db"
python scripts/export_market_data.py --out ./data/market

# 导入（默认先清空上述表再写入；--no-clear 可关闭清空）
python scripts/import_market_data.py
python scripts/import_market_data.py --dir ./data/market --no-clear
```

- 导入会去掉 CSV 中的自增 `id`，由目标库重新分配  
- CLI 使用短连接超时，避免库不可达时长时间卡住  
- 逻辑：`scripts/market_data_io.py`；测试：`pytest tests/test_market_data_io.py -q`

---

## 风控硬规则

见 [`docs/hard-rules.md`](docs/hard-rules.md)。默认 **paper**；live 需 ARM + 白名单 + Kill Switch。

---

## Windows · TA-Lib

若需原生 TA-Lib，请安装对应 Python 版本的 wheel；未安装时自动使用 pandas 回退实现。

---

## QMT

未配置 miniQMT 或 `QMT_FORCE_MOCK=1` 时使用 `MockQmtBroker`。实盘需关闭强制 Mock，并满足硬规则中的闸门。

---

## 投研 · nanobot

投研页（`/ai`）支持**多轮流式对话**：侧栏勾选启用 Skills，点击名称查看详情；发送携带 `enabled_skills`。流式过程为纯文本，结束后按 Markdown / JSON 富文本展示。快捷提示可带 `skill_hint`；「新会话」清空历史。

**API**

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ai/skills` | 列出全部 skill |
| GET | `/api/ai/skills/{name}` | 单个 skill 描述与全文 |
| POST | `/api/ai/chat` | `{ messages, skill_hint?, enabled_skills? }`，流式文本 |
| GET | `/api/ai/financials/{symbol}` | 调试财务快照（`years` 默认 5） |

**LLM**：设置页或 `.env` 的 `LLM_*`。未配置时会提示去设置。

**联网搜索（可选）**：`.env` 设置 `TAVILY_API_KEY`；未配置时 `web_search` 不可用，五步法仍可走财务与知识库。

**财务**：缓存 → QMT `xtdata` → **akshare** 降级；响应带 `source`。

投研工具均为**只读**；禁止注册下单或解除 Kill Switch 类工具。

---

## 相关文档

| 文档 | 内容 |
| --- | --- |
| [`docs/v1.md`](docs/v1.md) | v1 冻结范围与技术选型 |
| [`docs/hard-rules.md`](docs/hard-rules.md) | 风控硬规则 |
| [`docs/architecture.md`](docs/architecture.md) | 架构说明 |
| `docs/superpowers/specs/` · `plans/` | 特性设计与实现计划 |
