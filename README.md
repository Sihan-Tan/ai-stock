# 刻度 Desk · 个人 AI 量化工作台

本地优先的个人 AI 量化交易系统（v1 范围已冻结）。

## 功能

行情监控、打板情绪、龙虎榜、交易日历/停牌、策略（Python/YAML/Agent）、backtrader 回测、模拟盘/QMT、飞书告警、LightGBM/XGBoost、晨会（含竞价强势池）、复盘、知识库、**投研对话 nanobot + Skill**。

## 快速开始

### 1. 数据库

```bash
docker compose up -d postgres
cp .env.example .env
```

无 Docker 时可临时使用 SQLite：

```bash
# Windows PowerShell
$env:DATABASE_URL="sqlite:///./data/desk.db"
```

### 2. Python

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
# 可选：pip install TA-Lib
```

### 3. API

```bash
cd apps/api
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：<http://127.0.0.1:8000/health>  
OpenAPI：<http://127.0.0.1:8000/docs>

种子数据示例：

```bash
curl -X POST http://127.0.0.1:8000/api/market/seed
curl -X POST http://127.0.0.1:8000/api/calendar/seed
curl -X POST http://127.0.0.1:8000/api/sentiment/seed
curl -X POST http://127.0.0.1:8000/api/lhb/seed
```

### 4. 前端

```bash
cd apps/web
npm install
npm run dev
```

### 5. 测试

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
