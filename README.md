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

### nanobot Skills

自建 skill 位于仓库根目录 `skills/`。投研 API：`GET /api/ai/skills`、`POST /api/ai/chat`。
