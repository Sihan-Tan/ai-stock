# 刻度 Desk · 个人 AI 量化工作台

本地优先的个人 AI 量化交易系统（v1 范围已冻结）。

## 功能

行情监控、打板情绪、龙虎榜、交易日历/停牌、策略（Python/YAML/Agent）、backtrader 回测、模拟盘/QMT、飞书告警、LightGBM/XGBoost、晨会（含竞价强势池）、复盘、知识库、**投研对话 nanobot + Skill**。

## 快速开始

### 根目录一键启动（推荐）

首次需先装好依赖（见下方「环境准备」）。之后在仓库根目录任选一条：

```powershell
# Windows PowerShell（推荐）
.\scripts\dev.ps1

# 或跨平台
python scripts/dev.py

# 或
npm run dev
```

行为说明：

- 同时前台启动 **FastAPI**（`127.0.0.1:8000`）与 **Vite**（`127.0.0.1:5173`）
- 前端 `/api`、`/health` 已代理到后台（见 `apps/web/vite.config.ts`）
- **Ctrl+C** 会结束两个子进程
- 若无 `.env`：从 `.env.example` 复制，并默认写入 `DATABASE_URL=sqlite:///./data/desk.db` 便于本地一键跑；若已有 `.env` 则尊重其配置
- 启动前会检查 Python（fastapi/uvicorn）与 `apps/web/node_modules`

健康检查：<http://127.0.0.1:8000/health>  
OpenAPI：<http://127.0.0.1:8000/docs>  
前端：<http://127.0.0.1:5173/>

### 环境准备

#### 1. 数据库与 `.env`

```bash
docker compose up -d postgres
cp .env.example .env
```

无 Docker 时可临时使用 SQLite（一键脚本在缺少 `.env` 时也会默认走这条）：

```powershell
# Windows PowerShell
$env:DATABASE_URL="sqlite:///./data/desk.db"
```

#### 2. Python

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
# 可选：pip install TA-Lib
```

#### 3. 前端依赖

```bash
cd apps/web
npm install
```

### 分开启动（可选）

```bash
# API（仓库根目录）
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir apps/api

# 前端
cd apps/web
npm run dev
```

种子数据已移除。数据请通过行情 / 情绪 / 龙虎榜 jobs 同步写入库。

### 测试

```bash
$env:DATABASE_URL="sqlite:///:memory:"
pytest -q
# 或本地 Mock CI：
# pwsh scripts/smoke_mock.ps1
```

### 风控硬规则

见 [`docs/hard-rules.md`](docs/hard-rules.md)。默认 paper；live 需 ARM + 白名单 + Kill Switch。

### Windows · TA-Lib

若需原生 TA-Lib，请安装对应 Python 版本的 wheel；未安装时自动使用 pandas 回退实现。

### QMT

未配置 miniQMT 时使用 `MockQmtBroker`；实盘需 ARM + 白名单 + Kill Switch。

### 投研 · nanobot

投研页（`/research`）支持**多轮对话**：前端累积 `messages` 随 `POST /api/ai/chat` 发送，流式展示答复；可选 `skill_hint` 指定场景 skill；「新会话」清空历史。

**API**

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ai/skills` | 列出全部 skill |
| POST | `/api/ai/chat` | 多轮对话（body: `{ messages, skill_hint? }`，流式文本） |
| GET | `/api/ai/financials/{symbol}` | 调试 / 验数，绕过 LLM 拉财务快照（query: `years`，默认 5） |

**LLM**：设置页配置 `llm_api_key` / `llm_base_url` / `llm_model`（或 `.env` 中 `LLM_*`）。未配置时对话会提示去设置页。

**联网搜索（可选）**：五步法 / `web_search` 工具需 Tavily Key。在 `.env` 设置 `TAVILY_API_KEY`；未配置时搜索工具不可用，五步法仍可基于财务与知识库并会在答复中说明。

**财务数据**：`FinancialService` 取数顺序为本地缓存 → QMT `xtdata` → **akshare** 自动降级；返回带 `source`（`qmt` / `akshare`）。QMT 不可用时仍可走 akshare（在数据源可用前提下）。

**Skills**（仓库根目录 `skills/`）

| Skill | 用途 |
| --- | --- |
| `investment-research` | 场景索引 |
| `financial-analysis` | 单股财务趋势 → `get_financials` |
| `peer-compare` | 同行对比 → `peer_compare` |
| `valuation` | 估值与分位 → `get_valuation` |
| `write-report` | 五步法研报 → 财务 + `web_search` + 知识库 |
| `desk-readonly` | 只读查自选 / 策略 / 知识库 |
| `knowledge-rag` | 知识库检索 |
| `strategy-yaml-author` | 策略 YAML 草稿（用户明确要求时） |
| `auction-strong-pick` | 竞价强势池 |

投研工具均为**只读**（含 `get_financials` / `peer_compare` / `get_valuation`）；禁止注册下单或解除 Kill Switch 类工具。详见 [`docs/hard-rules.md`](docs/hard-rules.md)。
