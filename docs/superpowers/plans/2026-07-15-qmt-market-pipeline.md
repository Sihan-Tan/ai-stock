# QMT 真实行情管道 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将刻度 Desk 行情主路径从 demo seed 切换为 QMT/`xtdata` 为主、AkShare 仅补洞/日历的真实行情管道，日线全 A（在市）长期落库（前复权默认列 + `_hfq`），分钟仅自选∪指数近 3 交易日，并由 APScheduler + API jobs 可观测调度。

**Architecture:** 在 `desk_market` 内新增与 `QmtBroker` 严格分离的 `qmt_md` 适配层（Protocol + Mock + xtdata 实现）；`DailyBarIngestor` / `HistoryBackfill` / `MinuteBarIngestor` / `SecurityListSync` / `CalendarSync` 经交易日门闸写入 `bars_daily` / `bars_minute` / `trade_calendar`；APScheduler 挂在 FastAPI `lifespan`；API 暴露手动触发与 `jobs/status`；回测 `MarketService.load_daily_df` 默认读前复权列，可切 `hfq`。

**Tech Stack:** Python 3.11+、SQLAlchemy 2、Alembic、FastAPI、APScheduler、pandas、AkShare、miniQMT `xtquant.xtdata`（可选依赖，测试一律 Mock）、pytest、PyYAML、pydantic-settings。

---

## File Structure

| 路径 | 职责 |
|------|------|
| `configs/market/indices.yaml` | 分钟宇宙指数列表（沪深300/上证/深成/创业板等） |
| `configs/market/sync.yaml` | `daily_start_date`、日终近 N 日、批大小、调度 cron/间隔默认值 |
| `packages/common/desk_common/settings.py` | 增补 `market_daily_start`、`market_incremental_days`、调度相关 Settings（env 覆盖 YAML） |
| `packages/market/desk_market/config.py` | 加载 `configs/market/*.yaml`，与 Settings 合并为 `MarketSyncConfig` |
| `packages/db/desk_db/models.py` | `BarDaily` 增 `_hfq` 列；新增 `SecurityMeta`、`MarketJobRun` |
| `alembic/versions/0002_bars_daily_hfq_jobs.py` | 生产库 `ALTER` 加列 + 建新表（SQLite 测试仍靠 `create_all`） |
| `packages/market/desk_market/qmt_md.py` | `QmtMarketData` Protocol、`InstrumentInfo`、`MockQmtMarketData`、`XtdataMarketData`（与 `desk_broker.QmtBroker` 分离） |
| `packages/market/desk_market/akshare_daily.py` | AkShare 日线补洞适配（前/后复权语义对齐后输出同结构 DataFrame） |
| `packages/market/desk_market/security_universe.py` | `SecurityListSync`：过滤退市 → 在市宇宙；可选更新 `SecurityMeta` |
| `packages/market/desk_market/daily_ingest.py` | `DailyBarIngestor`：日终近 N 日增量 upsert（默认列 + `_hfq`） |
| `packages/market/desk_market/history_backfill.py` | `HistoryBackfill`：缺口检测（≥ `daily_start_date`）、QMT→AkShare |
| `packages/market/desk_market/minute_ingest.py` | 自选∪指数分钟 upsert + `purge_minute_older_than_3td` |
| `packages/market/desk_market/job_store.py` | `MarketJobRun` 写入/查询，供 `GET /jobs/status` |
| `packages/market/desk_market/jobs.py` | 各 job 编排入口（日历/证券列表/日终/回填/分钟），统一记 status |
| `packages/market/desk_market/scheduler.py` | 创建/注册/shutdown `BackgroundScheduler` |
| `packages/market/desk_market/__init__.py` | 保留并扩展 `MarketService`（upsert/load 支持 hfq、分钟 upsert/purge、seed 双列）；re-export 新模块公开 API |
| `packages/calendar/desk_calendar/__init__.py` | 增补 `CalendarSync`（AkShare→`trade_calendar`）；`is_trade_day` 保留周末 fallback + 「日历未同步」日志钩子 |
| `packages/backtest/desk_backtest/__init__.py` | `BacktraderRunner` / `load_daily_df` 传递 `adj`（默认前复权） |
| `apps/api/app/__init__.py` | `lifespan` 启动 scheduler、关闭 shutdown |
| `apps/api/app/routes/market.py` | 新增 jobs/bars/intraday 契约；保留 seed |
| `apps/web/src/App.tsx` | Overview：seed 降为次要入口文案（注明覆盖同键假数据） |
| `tests/test_market_pipeline_upsert.py` | 日线默认列 + `_hfq` 幂等 upsert |
| `tests/test_market_pipeline_delist.py` | 退市过滤（Mock InstrumentStatus） |
| `tests/test_market_pipeline_backfill.py` | `daily_start_date` 下界、QMT→AkShare、日终仅近 N 日 |
| `tests/test_market_pipeline_minute.py` | 分钟 upsert + 3 交易日 purge |
| `tests/test_market_pipeline_api.py` | API contracts + jobs/status |
| `tests/test_market_pipeline_feed.py` | DataFeed `adj` 映射 |
| `tests/test_market_pipeline_calendar.py` | 日历同步 / 未同步日志 / 节假日门闸 |

**不做（本计划外）：** 实盘下单、行情塞进 `QmtBroker`、全 A 分钟、删 seed、未复权落库、`adj_type` 分行、清退市历史日线。

---

### Task 1: 配置文件 + Settings + MarketSyncConfig

**Files:**
- Create: `configs/market/indices.yaml`
- Create: `configs/market/sync.yaml`
- Create: `packages/market/desk_market/config.py`
- Modify: `packages/common/desk_common/settings.py`
- Test: `tests/test_market_pipeline_config.py`

- [ ] **Step 1: Write the failing test**

```python
"""MarketSyncConfig 加载与 Settings 覆盖。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from desk_common.settings import get_settings
from desk_market.config import load_market_sync_config, load_indices


def test_load_indices_yaml(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "indices.yaml"
    cfg.write_text(
        "indices:\n  - symbol: 000300.SH\n    name: 沪深300\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_INDICES_YAML", str(cfg))
    get_settings.cache_clear()
    symbols = load_indices()
    assert "000300.SH" in symbols


def test_daily_start_date_default_and_env_override(monkeypatch, tmp_path: Path):
    sync = tmp_path / "sync.yaml"
    sync.write_text(
        "daily_start_date: '2018-01-01'\nincremental_days: 2\nbatch_size: 50\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_SYNC_YAML", str(sync))
    monkeypatch.delenv("MARKET_DAILY_START", raising=False)
    get_settings.cache_clear()
    cfg = load_market_sync_config()
    assert cfg.daily_start_date == date(2018, 1, 1)
    assert cfg.incremental_days == 2

    monkeypatch.setenv("MARKET_DAILY_START", "2020-06-01")
    get_settings.cache_clear()
    cfg2 = load_market_sync_config()
    assert cfg2.daily_start_date == date(2020, 6, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run (PowerShell):

```powershell
pytest tests/test_market_pipeline_config.py -v
```

Expected: FAIL（`desk_market.config` 或属性不存在）

- [ ] **Step 3: Write minimal implementation**

`configs/market/indices.yaml`:

```yaml
indices:
  - symbol: "000300.SH"
    name: "沪深300"
  - symbol: "000001.SH"
    name: "上证综指"
  - symbol: "399001.SZ"
    name: "深成指"
  - symbol: "399006.SZ"
    name: "创业板指"
```

`configs/market/sync.yaml`:

```yaml
daily_start_date: "2018-01-01"
incremental_days: 3
batch_size: 100
# 调度默认意图（可被 Settings 覆盖）
jobs:
  sync_trade_calendar: { cron: "0 2 * * *" }
  sync_security_list: { cron: "0 15 * * 1-5" }
  ingest_daily_incremental: { cron: "30 15 * * 1-5" }
  backfill_daily_chunks: { cron: "0 1 * * *" }
  ingest_minute_watch: { minutes: 3 }
  purge_with_minute: true
```

在 `Settings` 增补：

```python
market_daily_start: str = "2018-01-01"  # env: MARKET_DAILY_START
market_incremental_days: int = 3
market_batch_size: int = 100
market_sync_yaml: str = "configs/market/sync.yaml"
market_indices_yaml: str = "configs/market/indices.yaml"
market_scheduler_enabled: bool = True
```

`packages/market/desk_market/config.py`：用 `yaml.safe_load` 读文件；`MarketSyncConfig` dataclass 字段：`daily_start_date: date`、`incremental_days`、`batch_size`、`jobs: dict`；**Settings.env 优先于 YAML**（`MARKET_DAILY_START` → `date.fromisoformat`）。

`load_indices() -> list[str]`：读 YAML `indices[].symbol`，经 `normalize_symbol`。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add configs/market/indices.yaml configs/market/sync.yaml packages/common/desk_common/settings.py packages/market/desk_market/config.py tests/test_market_pipeline_config.py
git commit -m "feat(market): add sync/indices config and MARKET_DAILY_START"
```

---

### Task 2: BarDaily `_hfq` + SecurityMeta + MarketJobRun + Alembic

**Files:**
- Modify: `packages/db/desk_db/models.py`
- Create: `alembic/versions/0002_bars_daily_hfq_jobs.py`
- Test: `tests/test_market_pipeline_models.py`

- [ ] **Step 1: Write the failing test**

```python
"""ORM 列与唯一键。"""

from datetime import date, datetime

from sqlalchemy import select

from desk_db import Base, get_engine
from desk_db.models import BarDaily, MarketJobRun, SecurityMeta


def test_bar_daily_has_hfq_columns(_db):
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    assert hasattr(BarDaily, "open_hfq")
    assert hasattr(BarDaily, "close_hfq")
    assert hasattr(BarDaily, "volume_hfq")
    # 默认列无 _qfq 后缀
    assert not hasattr(BarDaily, "open_qfq")


def test_security_meta_and_job_run(_db):
    assert SecurityMeta.__tablename__ == "security_meta"
    assert MarketJobRun.__tablename__ == "market_job_runs"
```

说明：仓库会话工厂为 `desk_db.get_session_factory()`（见 `packages/db/desk_db/__init__.py`）；测试侧与既有 `_db` fixture 一样先 `get_engine()` + `create_all`，再用 `Session(get_engine())` 或 `get_session_factory()()`。推荐列断言：

```python
def test_bars_daily_columns_present(_db):
    cols = set(BarDaily.__table__.c.keys())
    for name in ("open", "high", "low", "close", "volume", "amount",
                 "open_hfq", "high_hfq", "low_hfq", "close_hfq", "volume_hfq", "adj_factor"):
        assert name in cols
    assert "open_qfq" not in cols
    assert "uq_bars_daily_symbol_ts" in {c.name for c in BarDaily.__table__.constraints
                                         if hasattr(c, "name") and c.name}
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_models.py -v
```

Expected: FAIL（缺 `_hfq` / 新表）

- [ ] **Step 3: Write minimal implementation**

在 `BarDaily` 增加（`amount` 默认与前复权共用，本期不加 `amount_hfq`）：

```python
open_hfq: Mapped[float | None] = mapped_column(Float, nullable=True)
high_hfq: Mapped[float | None] = mapped_column(Float, nullable=True)
low_hfq: Mapped[float | None] = mapped_column(Float, nullable=True)
close_hfq: Mapped[float | None] = mapped_column(Float, nullable=True)
volume_hfq: Mapped[float | None] = mapped_column(Float, nullable=True)
```

新增：

```python
class SecurityMeta(Base):
    __tablename__ = "security_meta"
    __table_args__ = (UniqueConstraint("symbol", name="uq_security_meta_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    is_delisted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="listed")  # listed|delisted|...
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketJobRun(Base):
    __tablename__ = "market_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ok|failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    symbols_done: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
```

Alembic `0002`：`down_revision = "0001_initial"`；`upgrade` 对 Postgres/MySQL 用 `op.add_column`；对缺失表 `op.create_table`。SQLite 开发可用 `batch_alter_table`。若检测方言过于琐碎：可 `try/except` 或文档注明「测试库 create_all；生产 alembic upgrade」。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_models.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/db/desk_db/models.py alembic/versions/0002_bars_daily_hfq_jobs.py tests/test_market_pipeline_models.py
git commit -m "feat(db): add BarDaily hfq columns, SecurityMeta, MarketJobRun"
```

---

### Task 3: MarketService upsert/load 前复权默认列 + `_hfq`（TDD）

**Files:**
- Modify: `packages/market/desk_market/__init__.py`（`upsert_daily_bars` / `load_daily_df` / `seed_demo_data`）
- Test: `tests/test_market_pipeline_upsert.py`

- [ ] **Step 1: Write the failing test**

```python
"""日线 upsert 幂等：默认列 + _hfq。"""

from datetime import date

import pandas as pd
from sqlalchemy import func, select

from desk_db import get_engine
from desk_db.models import BarDaily
from desk_market import MarketService
from sqlalchemy.orm import Session


def _session():
    engine = get_engine()
    return Session(engine)


def test_upsert_daily_bars_writes_hfq_and_is_idempotent(_db):
    db = _session()
    svc = MarketService(db)
    df = pd.DataFrame(
        [
            {
                "date": date(2024, 1, 2),
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000,
                "amount": 10500,
                "open_hfq": 100.0,
                "high_hfq": 110.0,
                "low_hfq": 95.0,
                "close_hfq": 105.0,
                "volume_hfq": 1000,
            }
        ]
    )
    assert svc.upsert_daily_bars("600519.SH", df) == 1
    db.commit()
    # 覆盖更新
    df2 = df.copy()
    df2["close"] = 10.8
    df2["close_hfq"] = 108.0
    assert svc.upsert_daily_bars("600519.SH", df2) == 1
    db.commit()
    n = db.scalar(select(func.count()).select_from(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert n == 1
    row = db.scalar(select(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert row.close == 10.8
    assert row.close_hfq == 108.0
    assert row.open == 10.0


def test_load_daily_df_adj_qfq_default_and_hfq(_db):
    db = _session()
    svc = MarketService(db)
    svc.upsert_daily_bars(
        "600519.SH",
        pd.DataFrame(
            [
                {
                    "date": date(2024, 1, 2),
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "volume": 1,
                    "amount": 1,
                    "open_hfq": 100.0,
                    "high_hfq": 110.0,
                    "low_hfq": 95.0,
                    "close_hfq": 105.0,
                    "volume_hfq": 1,
                }
            ]
        ),
    )
    db.commit()
    qfq = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 3), adj="qfq")
    assert float(qfq.iloc[0]["close"]) == 10.5
    hfq = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 3), adj="hfq")
    assert float(hfq.iloc[0]["close"]) == 105.0
    default = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 3))
    assert float(default.iloc[0]["close"]) == 10.5
```

**约定（写入策略）：** 仅当默认列 OHLCV 与 `*_hfq` **齐备**才 upsert；缺一侧则跳过该行并可由调用方记入错误列表（本方法可返回写入数，跳过不计或抛 `ValueError`——推荐：跳过 + 返回 `(written, skipped)` 元组会破坏现有 int API，故保持 `int`，缺侧跳过不计写入；ingest 层负责记错误）。

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_upsert.py -v
```

Expected: FAIL（`upsert` 未写 hfq / `adj` 参数不存在）

- [ ] **Step 3: Write minimal implementation**

扩展 `upsert_daily_bars`：读 `open_hfq`…`volume_hfq`；两套都有才写入；更新时同时覆盖默认列与 `_hfq`。

扩展 `load_daily_df(..., adj: str | None = None)`：
- `adj is None` 或 `adj in {"qfq", "forward"}` → 默认列映射为 open/high/low/close/volume
- `adj == "hfq"` → 用 `*_hfq` 映射到同名 open/high/low/close/volume（feed 友好）

`seed_demo_data`：生成行时复制相同数值到 `*_hfq`。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_upsert.py -v
```

Expected: PASS；并确认既有：

```powershell
pytest tests/test_core.py::test_market_seed_and_watchlist tests/test_core.py::test_backtest_ma_cross -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/__init__.py tests/test_market_pipeline_upsert.py
git commit -m "feat(market): upsert/load daily bars with default qfq and hfq columns"
```

---

### Task 4: `qmt_md` Protocol + Mock（与 QmtBroker 分离）

**Files:**
- Create: `packages/market/desk_market/qmt_md.py`
- Test: `tests/test_market_pipeline_qmt_md.py`

- [ ] **Step 1: Write the failing test**

```python
"""MockQmtMarketData：列表过滤与双复权日线。"""

from datetime import date

from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData


def test_list_instruments_filters_delisted():
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo(symbol="600519.SH", name="茅台", status="listed"),
            InstrumentInfo(symbol="000001.SZ", name="退市样例", status="delisted"),
        ]
    )
    active = md.list_a_share_symbols(include_delisted=False)
    assert active == ["600519.SH"]
    assert "000001.SZ" in md.list_a_share_symbols(include_delisted=True)


def test_get_daily_bars_returns_qfq_and_hfq_columns():
    md = MockQmtMarketData()
    md.seed_daily(
        "600519.SH",
        date(2024, 1, 2),
        qfq={"open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1, "amount": 1},
        hfq={"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1},
    )
    df = md.get_daily_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 3))
    assert "close" in df.columns and "close_hfq" in df.columns
    assert float(df.iloc[0]["close"]) == 10.5
    assert float(df.iloc[0]["close_hfq"]) == 105.0


def test_get_minute_and_snapshot_readonly():
    md = MockQmtMarketData()
    md.seed_minute("600519.SH", "2024-01-02 09:31:00", open=10, high=10, low=10, close=10, volume=1)
    m = md.get_minute_bars("600519.SH", start="2024-01-02 09:30:00", end="2024-01-02 15:00:00")
    assert len(m) == 1
    q = md.get_snapshots(["600519.SH"])
    assert "600519.SH" in q
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_qmt_md.py -v
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: Write minimal implementation**

`qmt_md.py` 要点：

```python
from typing import Protocol
from dataclasses import dataclass
import pandas as pd

@dataclass
class InstrumentInfo:
    symbol: str
    name: str = ""
    status: str = "listed"  # listed|delisted|suspended；Mock 用字符串，真实 xtdata 映射到此


class QmtMarketData(Protocol):
    def list_instruments(self) -> list[InstrumentInfo]: ...
    def list_a_share_symbols(self, include_delisted: bool = False) -> list[str]: ...
    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...
    def get_minute_bars(self, symbol: str, start: str | datetime, end: str | datetime) -> pd.DataFrame: ...
    def get_snapshots(self, symbols: list[str]) -> dict[str, dict]: ...


class MockQmtMarketData:
    """单测用；固定 InstrumentStatus / OHLCV。"""
    ...


class XtdataMarketData:
    """
    真实 xtquant.xtdata 适配。
    不可 import 时构造失败或降级由上层 jobs 标记 failed。
    禁止依赖 desk_broker.QmtBroker。
    """
    def __init__(self):
        from xtquant import xtdata  # type: ignore
        self._xt = xtdata
```

`get_daily_bars` 对真实实现：分别取前复权与后复权（或两次请求），合并为默认列 + `_hfq` 列；符号一律 `normalize_symbol`。字段名以联调文档为准，在适配层集中映射，测试只打 Mock。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_qmt_md.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/qmt_md.py tests/test_market_pipeline_qmt_md.py
git commit -m "feat(market): add qmt_md Protocol and MockQmtMarketData"
```

---

### Task 5: 退市过滤 + SecurityListSync

**Files:**
- Create: `packages/market/desk_market/security_universe.py`
- Test: `tests/test_market_pipeline_delist.py`

- [ ] **Step 1: Write the failing test**

```python
"""退市不进入在市宇宙；已有退市日线不再被增量更新。"""

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db import get_engine
from desk_db.models import BarDaily, SecurityMeta
from desk_market import MarketService
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_market.security_universe import SecurityListSync
from desk_market.daily_ingest import DailyBarIngestor


def test_security_list_sync_marks_and_filters(_db):
    db = Session(get_engine())
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo("600519.SH", "茅台", "listed"),
            InstrumentInfo("999999.SH", "已退", "delisted"),
        ]
    )
    sync = SecurityListSync(db, md)
    universe = sync.run()
    assert universe == ["600519.SH"]
    meta = {m.symbol: m for m in db.scalars(select(SecurityMeta)).all()}
    assert meta["999999.SH"].is_delisted is True
    assert meta["600519.SH"].is_delisted is False
    db.commit()


def test_incremental_skips_delisted_and_does_not_update_existing(_db):
    db = Session(get_engine())
    svc = MarketService(db)
    # 库内已有退市标的历史
    svc.upsert_daily_bars(
        "999999.SH",
        pd.DataFrame(
            [
                {
                    "date": date(2023, 1, 3),
                    "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1,
                    "open_hfq": 1, "high_hfq": 1, "low_hfq": 1, "close_hfq": 1, "volume_hfq": 1,
                }
            ]
        ),
    )
    db.commit()
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo("600519.SH", "茅台", "listed"),
            InstrumentInfo("999999.SH", "已退", "delisted"),
        ]
    )
    md.seed_daily(
        "999999.SH",
        date(2024, 1, 2),
        qfq={"open": 9, "high": 9, "low": 9, "close": 9, "volume": 9, "amount": 9},
        hfq={"open": 9, "high": 9, "low": 9, "close": 9, "volume": 9},
    )
    md.seed_daily(
        "600519.SH",
        date(2024, 1, 2),
        qfq={"open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "amount": 1},
        hfq={"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
    )
    SecurityListSync(db, md).run()
    ing = DailyBarIngestor(db, md, symbols=None, incremental_days=3, asof=date(2024, 1, 2))
    ing.run()
    db.commit()
    # 退市不应新增 2024 行
    rows = db.scalars(select(BarDaily).where(BarDaily.symbol == "999999.SH")).all()
    assert len(rows) == 1 and rows[0].ts == date(2023, 1, 3)
    assert db.scalar(select(BarDaily).where(BarDaily.symbol == "600519.SH", BarDaily.ts == date(2024, 1, 2)))
```

注：本 Task 若 `DailyBarIngestor` 尚未实现，先只测 `SecurityListSync`；下一步 Task 6 实现 ingest 后补上第二用例——**推荐本 Task 只提交 SecurityListSync 测试与实现，第二用例放 Task 6**。为避免依赖未完成代码，Task 5 仅保留 `test_security_list_sync_marks_and_filters`。

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_delist.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`SecurityListSync.run() -> list[str]`：
1. `md.list_instruments()`
2. upsert `SecurityMeta`（`is_delisted = status == "delisted"`）
3. 返回 `status == "listed"` 的 symbol 列表（normalize）

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_delist.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/security_universe.py tests/test_market_pipeline_delist.py
git commit -m "feat(market): sync security list and filter delisted universe"
```

---

### Task 6: DailyBarIngestor（日终近 N 日，不受起始日回补驱动）

**Files:**
- Create: `packages/market/desk_market/daily_ingest.py`
- Modify: `tests/test_market_pipeline_delist.py`（补退市跳过用例）
- Test: `tests/test_market_pipeline_backfill.py`（本 Task 放日终近 N 日断言；回填下界在 Task 7）

- [ ] **Step 1: Write the failing test**

```python
"""日终增量只请求近 N 日。"""

from datetime import date

from desk_market.daily_ingest import DailyBarIngestor
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_market.security_universe import SecurityListSync
from sqlalchemy.orm import Session
from desk_db import get_engine


class RecordingMd(MockQmtMarketData):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        return super().get_daily_bars(symbol, start, end)


def test_incremental_requests_only_near_window(_db):
    db = Session(get_engine())
    md = RecordingMd(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date(2024, 6, 3),
        qfq={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1},
        hfq={"open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
    )
    SecurityListSync(db, md).run()
    DailyBarIngestor(
        db, md, symbols=None, incremental_days=2, asof=date(2024, 6, 3), daily_start_date=date(2018, 1, 1)
    ).run()
    assert md.calls
    for _, start, end in md.calls:
        assert start >= date(2024, 6, 2)  # 近 2 日窗（含 asof 往前 N-1）
        assert end <= date(2024, 6, 3)
        assert start >= date(2018, 1, 1)  # 不下探起始日之前，但也不为对齐起始日扩窗
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_backfill.py::test_incremental_requests_only_near_window -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
class DailyBarIngestor:
    """
    全 A 在市日终增量。
    只拉 [asof-(N-1), asof]；不因 daily_start_date 扩成历史全量。
    """
    def __init__(self, db, md, symbols=None, incremental_days=3, asof=None, daily_start_date=None):
        ...

    def run(self) -> dict:
        # symbols or SecurityMeta 中 is_delisted=False
        # 对每标的 get_daily_bars；半截复权行跳过记 errors
        # MarketService.upsert_daily_bars
        # return {"symbols_done": n, "errors": [...]}
```

把 Task 5 的退市跳过用例一并加入并实现。

- [ ] **Step 4: Run tests**

```powershell
pytest tests/test_market_pipeline_backfill.py::test_incremental_requests_only_near_window tests/test_market_pipeline_delist.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/daily_ingest.py tests/test_market_pipeline_backfill.py tests/test_market_pipeline_delist.py
git commit -m "feat(market): DailyBarIngestor near-window incremental upsert"
```

---

### Task 7: HistoryBackfill（缺口 ≥ daily_start_date，QMT→AkShare）

**Files:**
- Create: `packages/market/desk_market/akshare_daily.py`
- Create: `packages/market/desk_market/history_backfill.py`
- Modify: `tests/test_market_pipeline_backfill.py`

- [ ] **Step 1: Write the failing test**

```python
"""回填下界与 QMT→AkShare 降级。"""

from datetime import date

import pandas as pd

from desk_market.history_backfill import HistoryBackfill
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_market.akshare_daily import AkshareDailyClient
from sqlalchemy.orm import Session
from desk_db import get_engine
from desk_db.models import BarDaily
from sqlalchemy import select


class FailThenEmptyMd(MockQmtMarketData):
    def get_daily_bars(self, symbol, start, end):
        # 模拟空洞：返回空，迫使 AkShare
        return pd.DataFrame()


class FakeAk:
    def __init__(self):
        self.calls = []

    def get_daily_bars(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        return pd.DataFrame(
            [
                {
                    "date": date(2019, 1, 2),
                    "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1,
                    "open_hfq": 10, "high_hfq": 10, "low_hfq": 10, "close_hfq": 10, "volume_hfq": 1,
                }
            ]
        )


def test_backfill_clamps_to_daily_start_and_does_not_request_before(_db):
    db = Session(get_engine())
    md = FailThenEmptyMd(instruments=[InstrumentInfo("600519.SH", status="listed")])
    ak = FakeAk()
    fb = HistoryBackfill(
        db,
        md,
        akshare=ak,
        daily_start_date=date(2018, 1, 1),
        symbols=["600519.SH"],
        # 人为声称缺口含 2017（应被裁剪）
        forced_gap=(date(2017, 1, 1), date(2019, 1, 5)),
    )
    fb.run()
    assert ak.calls
    _, start, end = ak.calls[0]
    assert start == date(2018, 1, 1)
    assert start >= date(2018, 1, 1)


def test_backfill_prefers_qmt_then_akshare(_db):
    db = Session(get_engine())
    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date(2019, 6, 3),
        qfq={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1},
        hfq={"open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
    )
    ak = FakeAk()
    HistoryBackfill(
        db, md, akshare=ak, daily_start_date=date(2018, 1, 1),
        symbols=["600519.SH"], forced_gap=(date(2019, 6, 3), date(2019, 6, 3)),
    ).run()
    assert not ak.calls  # QMT 已返回数据
    row = db.scalar(select(BarDaily).where(BarDaily.symbol == "600519.SH"))
    assert row is not None and row.close_hfq == 2.0
```

缺口检测生产逻辑：对每个在市 symbol，取库内 `MAX(ts)` 与交易日集合差集，窗口裁剪到 `[daily_start_date, asof]`；`forced_gap` 仅测用参数。

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_backfill.py -v
```

Expected: FAIL（缺 HistoryBackfill / Akshare）

- [ ] **Step 3: Write minimal implementation**

`AkshareDailyClient.get_daily_bars`：内部可调 `ak.stock_zh_a_hist`（前复权/后复权各一次或等价），输出与 `qmt_md` 相同列；测试注入 Fake。失败时抛异常由 Backfill 捕获，缺口保持待回填。

`HistoryBackfill.run`：
1. 跳过 `is_delisted`
2. 计算缺口 ∩ `[daily_start_date, …]`
3. 先 `md.get_daily_bars`；空/异常 → `akshare.get_daily_bars`
4. 齐备复权才 upsert

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_backfill.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/akshare_daily.py packages/market/desk_market/history_backfill.py tests/test_market_pipeline_backfill.py
git commit -m "feat(market): HistoryBackfill with daily_start_date and AkShare fill"
```

---

### Task 8: CalendarSync + 交易日门闸日志

**Files:**
- Modify: `packages/calendar/desk_calendar/__init__.py`
- Test: `tests/test_market_pipeline_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
"""日历同步与未同步提示。"""

from datetime import date
import logging

from desk_calendar import CalendarService, CalendarSync


class FakeAkCal:
    def trade_days(self, start: date, end: date) -> list[tuple[date, bool]]:
        return [
            (date(2024, 1, 1), False),  # 元旦
            (date(2024, 1, 2), True),
        ]


def test_calendar_sync_upserts(_db):
    from sqlalchemy.orm import Session
    from desk_db import get_engine

    db = Session(get_engine())
    n = CalendarSync(db, client=FakeAkCal()).run(date(2024, 1, 1), date(2024, 1, 2))
    assert n >= 2
    svc = CalendarService(db)
    assert svc.is_trade_day(date(2024, 1, 1)) is False
    assert svc.is_trade_day(date(2024, 1, 2)) is True


def test_is_trade_day_logs_when_calendar_missing(caplog, _db):
    from sqlalchemy.orm import Session
    from desk_db import get_engine

    db = Session(get_engine())
    svc = CalendarService(db)
    with caplog.at_level(logging.WARNING):
        assert svc.is_trade_day(date(2024, 5, 1)) is True  # 周三 fallback，但若查库无记录
        # 实现：无行时 fallback 并打「日历未同步」
    assert any("日历未同步" in r.message for r in caplog.records)
```

注意：5/1 可能是节假日——测试用明确的「库中无该日记录」的日期即可；实现里**只要该 `cal_date` 无行**就打日志。

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_calendar.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`CalendarSync`：AkShare `tool_trade_date_hist_sina`（或项目惯用接口）→ upsert `TradeCalendar`；可注入 `client`。

`CalendarService.is_trade_day`：无行时 `logger.warning("日历未同步，使用周末 fallback: %s", day)` 后 `weekday < 5`。

提供 `require_trade_day(day) -> bool` 供 jobs 门闸：非交易日跳过。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_calendar.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/calendar/desk_calendar/__init__.py tests/test_market_pipeline_calendar.py
git commit -m "feat(calendar): CalendarSync from AkShare and unsynced warning"
```

---

### Task 9: 分钟 ingest + 近 3 交易日 purge

**Files:**
- Create: `packages/market/desk_market/minute_ingest.py`
- Modify: `packages/market/desk_market/__init__.py`（`upsert_minute_bars` / `purge_minute_before`）
- Test: `tests/test_market_pipeline_minute.py`

- [ ] **Step 1: Write the failing test**

```python
"""分钟宇宙与 3 交易日 purge。"""

from datetime import date, datetime

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from desk_db import get_engine
from desk_db.models import BarMinute, TradeCalendar, WatchlistItem
from desk_market import MarketService
from desk_market.minute_ingest import MinuteBarIngestor, compute_minute_purge_cutoff
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData


def _seed_calendar(db, days: list[tuple[date, bool]]):
    for d, open_ in days:
        db.add(TradeCalendar(cal_date=d, is_open=open_))
    db.flush()


def test_purge_keeps_only_last_3_trade_days(_db):
    db = Session(get_engine())
    # 交易日：1,2,3,4,5；周末不计
    _seed_calendar(
        db,
        [
            (date(2024, 1, 2), True),
            (date(2024, 1, 3), True),
            (date(2024, 1, 4), True),
            (date(2024, 1, 5), True),
            (date(2024, 1, 8), True),  # 当前交易日
        ],
    )
    svc = MarketService(db)
    for d in [2, 3, 4, 5, 8]:
        svc.upsert_minute_bars(
            "600519.SH",
            pd.DataFrame(
                [
                    {
                        "ts": datetime(2024, 1, d, 10, 0, 0),
                        "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1,
                    }
                ]
            ),
        )
    db.commit()
    # 当前=1/8，往前 3 个交易日=1/5,1/4,1/3；第 4 个=1/2 → cutoff=2024-01-02 09:30 Asia/Shanghai
    cutoff = compute_minute_purge_cutoff(db, asof=date(2024, 1, 8))
    assert cutoff == datetime(2024, 1, 2, 9, 30, 0)
    deleted = svc.purge_minute_before(cutoff)
    assert deleted >= 1
    left = db.scalars(select(BarMinute)).all()
    assert all(r.ts >= cutoff for r in left)
    assert {r.ts.day for r in left} <= {3, 4, 5, 8}


def test_minute_universe_watchlist_union_indices_skips_delisted(_db, tmp_path, monkeypatch):
    db = Session(get_engine())
    db.add(WatchlistItem(symbol="600519.SH", name="茅台"))
    db.add(WatchlistItem(symbol="999999.SH", name="退市自选"))
    db.flush()
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo("600519.SH", status="listed"),
            InstrumentInfo("999999.SH", status="delisted"),
            InstrumentInfo("000300.SH", status="listed"),
        ]
    )
    from desk_market.security_universe import SecurityListSync

    SecurityListSync(db, md).run()
    md.seed_minute("600519.SH", "2024-01-08 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    md.seed_minute("000300.SH", "2024-01-08 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    md.seed_minute("999999.SH", "2024-01-08 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    ing = MinuteBarIngestor(db, md, index_symbols=["000300.SH"], asof=date(2024, 1, 8))
    result = ing.run()
    db.commit()
    syms = {r.symbol for r in db.scalars(select(BarMinute)).all()}
    assert "600519.SH" in syms and "000300.SH" in syms
    assert "999999.SH" not in syms
```

`compute_minute_purge_cutoff`：取 `is_open=true` 且 `cal_date <= asof` 降序；第 4 个交易日的 `09:30`（naive 本地按 `Asia/Shanghai` 约定存库，测试用 naive datetime 与现有 `DateTime` 一致）。

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_minute.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`MarketService.upsert_minute_bars` / `purge_minute_before(cutoff) -> int`。

`MinuteBarIngestor`：宇宙 = watchlist ∪ indices，去掉 `is_delisted`；拉取分钟 upsert；可选末尾调用 purge。

分钟**不**要求 `_hfq` 双列。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_minute.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/minute_ingest.py packages/market/desk_market/__init__.py tests/test_market_pipeline_minute.py
git commit -m "feat(market): minute ingest for watchlist+indices and 3TD purge"
```

---

### Task 10: JobStore + jobs 编排（可观测失败）

**Files:**
- Create: `packages/market/desk_market/job_store.py`
- Create: `packages/market/desk_market/jobs.py`
- Test: `tests/test_market_pipeline_jobs.py`

- [ ] **Step 1: Write the failing test**

```python
"""任务运行记录与 QMT 断开可观测。"""

from desk_market.jobs import MarketJobs
from desk_market.job_store import JobStore
from desk_market.qmt_md import MockQmtMarketData
from sqlalchemy.orm import Session
from desk_db import get_engine
from desk_db.models import MarketJobRun
from sqlalchemy import select


class DeadMd(MockQmtMarketData):
    def get_daily_bars(self, *a, **k):
        raise RuntimeError("xtdata unavailable")


def test_job_records_failure_on_qmt_down(_db):
    db = Session(get_engine())
    jobs = MarketJobs(db, md=DeadMd(instruments=[]), akshare=None, config=None)
    # 允许空宇宙时仍标记一次失败；或先塞 listed 触发调用
    from desk_market.qmt_md import InstrumentInfo

    jobs = MarketJobs(
        db,
        md=DeadMd(instruments=[InstrumentInfo("600519.SH", status="listed")]),
        akshare=None,
        config=None,
    )
    out = jobs.ingest_daily_incremental(asof=None)
    assert out["status"] == "failed"
    row = db.scalars(select(MarketJobRun).where(MarketJobRun.job_id == "ingest_daily_incremental")).first()
    assert row is not None and row.status == "failed"
    assert "xtdata" in (row.error_summary or row.message).lower() or "unavailable" in row.error_summary.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_jobs.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`JobStore.start/finish` 写 `MarketJobRun`。

`MarketJobs` 方法与调度表对齐：
- `sync_trade_calendar`
- `sync_security_list`
- `ingest_daily_incremental`（交易日门闸）
- `backfill_daily_chunks`
- `ingest_minute_watch`（末尾可选 purge）
- `recent_status(limit=20) -> list[dict]`

QMT 整体不可用：catch → status=failed，**不清库**。单标的失败：errors 列表，不阻断整批（日终路径）。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_jobs.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/job_store.py packages/market/desk_market/jobs.py tests/test_market_pipeline_jobs.py
git commit -m "feat(market): job store and MarketJobs orchestration with failure status"
```

---

### Task 11: APScheduler 挂 lifespan

**Files:**
- Create: `packages/market/desk_market/scheduler.py`
- Modify: `apps/api/app/__init__.py`
- Test: `tests/test_market_pipeline_scheduler.py`

- [ ] **Step 1: Write the failing test**

```python
"""scheduler 工厂注册任务 ID。"""

from desk_market.scheduler import build_market_scheduler


def test_build_scheduler_registers_job_ids():
    # 使用关闭的 BackgroundScheduler，不 start 长时间跑
    sched, job_ids = build_market_scheduler(enabled=True, dry_run=True)
    expected = {
        "sync_trade_calendar",
        "sync_security_list",
        "ingest_daily_incremental",
        "backfill_daily_chunks",
        "ingest_minute_watch",
    }
    assert expected <= set(job_ids)
    sched.shutdown(wait=False)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_scheduler.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`build_market_scheduler`：读取 `MarketSyncConfig.jobs`；为每个 ID 包一层「开 Session → MarketJobs → commit」；`enabled=False` 或测试 env `MARKET_SCHEDULER_ENABLED=0` 时不注册。

`lifespan`：

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    scheduler = None
    if get_settings().market_scheduler_enabled:
        scheduler, _ = build_market_scheduler(enabled=True)
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
```

默认 cron 意图见 `sync.yaml`（15:30 日终、盘中分钟间隔、夜间回填、凌晨日历）。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_scheduler.py -v
```

Expected: PASS；健康检查仍过：

```powershell
pytest tests/test_core.py::test_health -v
```

- [ ] **Step 5: Commit**

```powershell
git add packages/market/desk_market/scheduler.py apps/api/app/__init__.py tests/test_market_pipeline_scheduler.py
git commit -m "feat(api): register APScheduler market jobs in lifespan"
```

---

### Task 12: API 契约（jobs / bars / intraday）

**Files:**
- Modify: `apps/api/app/routes/market.py`
- Test: `tests/test_market_pipeline_api.py`

- [ ] **Step 1: Write the failing test**

```python
"""Market API contracts。"""

from datetime import date

import pandas as pd
from desk_market import MarketService
from sqlalchemy.orm import Session
from desk_db import get_engine


def test_bars_daily_adj_and_jobs_status(client, _db, monkeypatch):
    # 注入 Mock md，避免真实 xtdata
    from desk_market.qmt_md import MockQmtMarketData, InstrumentInfo
    import app.routes.market as market_routes

    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date.today(),
        qfq={"open": 10, "high": 10, "low": 10, "close": 10.5, "volume": 1, "amount": 1},
        hfq={"open": 100, "high": 100, "low": 100, "close": 105, "volume": 1},
    )
    monkeypatch.setattr(market_routes, "get_market_data", lambda: md)

    db = Session(get_engine())
    MarketService(db).upsert_daily_bars(
        "600519.SH",
        pd.DataFrame(
            [
                {
                    "date": date(2024, 1, 2),
                    "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1, "amount": 1,
                    "open_hfq": 100, "high_hfq": 110, "low_hfq": 90, "close_hfq": 105, "volume_hfq": 1,
                }
            ]
        ),
    )
    db.commit()

    r = client.get("/api/market/bars/daily", params={"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-03"})
    assert r.status_code == 200
    assert r.json()[0]["close"] == 10.5
    r2 = client.get("/api/market/bars/daily", params={"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-03", "adj": "hfq"})
    assert r2.json()[0]["close"] == 105.0
    r3 = client.get("/api/market/bars/daily", params={"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-03", "adj": "qfq"})
    assert r3.json()[0]["close"] == 10.5

    assert client.post("/api/market/jobs/daily-sync").status_code == 200
    assert client.post("/api/market/jobs/minute-sync").status_code == 200
    assert client.post("/api/market/jobs/backfill").status_code == 200
    st = client.get("/api/market/jobs/status")
    assert st.status_code == 200
    assert isinstance(st.json(), list)


def test_seed_still_works(client):
    assert client.post("/api/market/seed").status_code == 200
```

路由清单（前缀已有 `/api` + `/market`）：

| Method | Path |
|--------|------|
| POST | `/jobs/daily-sync` |
| POST | `/jobs/minute-sync` |
| POST | `/jobs/backfill` |
| GET | `/bars/daily?symbol=&from=&to=&adj=` |
| GET | `/bars/minute?symbol=&from=&to=` |
| GET | `/intraday/quote?symbols=` |
| GET | `/jobs/status` |

保留 `POST /seed`、`GET|POST /watchlist`、`GET /boards`。

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_api.py -v
```

Expected: FAIL（404）

- [ ] **Step 3: Write minimal implementation**

在 `market.py` 组装 `MarketJobs`；`get_market_data()` 默认尝试 `XtdataMarketData`，失败则 `MockQmtMarketData` 空列表并让 job 失败可测路径通过 monkeypatch。

`GET /intraday/quote`：调用 `md.get_snapshots`，可不写库。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_api.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/routes/market.py tests/test_market_pipeline_api.py
git commit -m "feat(api): market jobs, bars, and intraday quote endpoints"
```

---

### Task 13: DataFeed / 回测 adj 切换

**Files:**
- Modify: `packages/backtest/desk_backtest/__init__.py`
- Modify: `packages/common/desk_common/contracts.py`（若 `BacktestRequest` 需可选 `adj`）
- Test: `tests/test_market_pipeline_feed.py`

- [ ] **Step 1: Write the failing test**

```python
"""DataFeed 默认前复权列，可切 hfq。"""

from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from desk_db import get_engine
from desk_market import MarketService
from desk_backtest import BacktraderRunner
from desk_common.contracts import BacktestRequest


def test_load_and_backtest_request_adj(_db):
    db = Session(get_engine())
    svc = MarketService(db)
    rows = []
    for i, d in enumerate([date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]):
        px = 10 + i
        rows.append(
            {
                "date": d,
                "open": px, "high": px, "low": px, "close": px, "volume": 1, "amount": 1,
                "open_hfq": px * 10, "high_hfq": px * 10, "low_hfq": px * 10,
                "close_hfq": px * 10, "volume_hfq": 1,
            }
        )
    svc.upsert_daily_bars("600519.SH", pd.DataFrame(rows))
    db.commit()
    df_q = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 10), adj="qfq")
    df_h = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 10), adj="hfq")
    assert float(df_q.iloc[0]["close"]) == 10.0
    assert float(df_h.iloc[0]["close"]) == 100.0
```

若为 `BacktestRequest` 增加 `adj: Literal["qfq","hfq"] = "qfq"`，则额外断言 runner 使用对应列（可对 `MarketService.load_daily_df` monkeypatch 检查调用参数）。

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_market_pipeline_feed.py -v
```

Expected: FAIL 仅当 runner 未传 adj；`load_daily_df` 若 Task 3 已完成则本测试应主要锁定 runner 接线。

- [ ] **Step 3: Write minimal implementation**

`BacktraderRunner.run`：`adj = getattr(req, "adj", "qfq")`；`self.market.load_daily_df(..., adj=adj)`。默认列映射 `_PandasData` 不变。

- [ ] **Step 4: Run test to verify it passes**

```powershell
pytest tests/test_market_pipeline_feed.py tests/test_core.py::test_backtest_ma_cross -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add packages/backtest/desk_backtest/__init__.py packages/common/desk_common/contracts.py tests/test_market_pipeline_feed.py
git commit -m "feat(backtest): map PandasData from qfq default or hfq columns"
```

---

### Task 14: seed 降级文案 + 总验收烟测

**Files:**
- Modify: `apps/web/src/App.tsx`（Overview 文案）
- Modify: `packages/market/desk_market/__init__.py`（确认 seed 写双侧列——Task 3 已做则复查）
- Test: 聚合命令（无需新文件或补一个 `tests/test_market_pipeline_acceptance.py` 调 Mock 全链路）

- [ ] **Step 1: Write acceptance smoke test**

```python
"""验收冒烟：Mock 全链路日终 + 分钟 purge + status。"""

from datetime import date, datetime

from desk_market.jobs import MarketJobs
from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData
from desk_market.config import load_market_sync_config
from sqlalchemy.orm import Session
from desk_db import get_engine
from desk_db.models import BarDaily, TradeCalendar, WatchlistItem
from sqlalchemy import select, func


def test_acceptance_mock_pipeline(_db):
    db = Session(get_engine())
    for d in [date(2024, 7, 1), date(2024, 7, 2), date(2024, 7, 3), date(2024, 7, 4)]:
        db.add(TradeCalendar(cal_date=d, is_open=True))
    db.add(WatchlistItem(symbol="600519.SH", name="茅台"))
    db.flush()
    md = MockQmtMarketData(instruments=[InstrumentInfo("600519.SH", status="listed")])
    md.seed_daily(
        "600519.SH",
        date(2024, 7, 4),
        qfq={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "amount": 1},
        hfq={"open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
    )
    md.seed_minute("600519.SH", "2024-07-04 09:31:00", open=1, high=1, low=1, close=1, volume=1)
    jobs = MarketJobs(db, md=md, akshare=None, config=load_market_sync_config())
    assert jobs.sync_security_list()["status"] == "ok"
    assert jobs.ingest_daily_incremental(asof=date(2024, 7, 4))["status"] in {"ok", "failed"}
    # 有数据时应为 ok
    assert db.scalar(select(func.count()).select_from(BarDaily).where(BarDaily.symbol == "600519.SH")) >= 1
    # 二次日终不增行
    n1 = db.scalar(select(func.count()).select_from(BarDaily))
    jobs.ingest_daily_incremental(asof=date(2024, 7, 4))
    n2 = db.scalar(select(func.count()).select_from(BarDaily))
    assert n1 == n2
```

Overview 文案改为类似：「演示数据（次要）：会覆盖同键假行情；日常请用真实同步 / jobs」。

- [ ] **Step 2: Run acceptance + 全市场管道测试**

```powershell
pytest tests/test_market_pipeline_*.py tests/test_core.py::test_market_seed_and_watchlist -v
```

Expected: PASS

- [ ] **Step 3: UI 文案修改**

```tsx
<p className="muted">
  日常请走真实行情同步。下方「注入演示数据」为无 QMT 冒烟入口，会覆盖同键假数据。
</p>
<button type="button" className="btn" onClick={seedAll}>
  注入演示数据（次要）
</button>
```

- [ ] **Step 4: Re-run UI-related API seed still works**

```powershell
pytest tests/test_core.py::test_market_seed_and_watchlist -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/App.tsx tests/test_market_pipeline_acceptance.py packages/market/desk_market/__init__.py
git commit -m "chore: demote seed UI and add mock pipeline acceptance smoke"
```

---

## Self-Review（相对 spec）

| Spec 要点 | 对应 Task |
|-----------|-----------|
| QMT xtdata 行情适配，与 QmtBroker 分离 | Task 4 |
| AkShare 补洞 + 日历 | Task 7、Task 8 |
| 全 A 日线长期落库；日终增量 + 分块回填 | Task 6、Task 7 |
| `daily_start_date` / `MARKET_DAILY_START` | Task 1、7 |
| 退市不过新入库；列表同步；历史保留停更 | Task 5、6 |
| 默认列=前复权（无 `_qfq`）；`_hfq` 宽表；默认读前复权；迁移 BarDaily | Task 2、3 |
| 分钟：自选∪指数，近 3 交易日 purge | Task 9 |
| APScheduler 任务表 | Task 10、11；默认 cron 在 `sync.yaml` |
| API contracts + job status | Task 12 |
| `indices.yaml` | Task 1 |
| seed 降级次要 | Task 3（双列）、Task 14 |
| 验收 / Mock xtdata | Task 4、14 及各单测 |
| DataFeed adj | Task 13 |
| 失败降级可观测、不清库 | Task 10 |
| 半截复权不 upsert | Task 3、6、7 |
| 不做：实盘下单、全 A 分钟、删 seed、未复权、`adj_type` 分行、清退市历史 | 文件结构「不做」声明 |

**Placeholder 扫描：** 无 TBD；测试与实现步骤含具体代码/命令。

**类型命名一致性：**
- `MockQmtMarketData` / `XtdataMarketData` / `QmtMarketData`
- `DailyBarIngestor` / `HistoryBackfill` / `MinuteBarIngestor` / `SecurityListSync` / `CalendarSync` / `MarketJobs` / `JobStore`
- `daily_start_date`、`incremental_days`、`adj in {None,"qfq","hfq"}`
- 列：`open_hfq`…`volume_hfq`（无 `open_qfq`）

**执行注意（Windows）：**
- 命令均可用 PowerShell：`pytest ... -v`
- 路径分隔可用正斜杠（pytest 兼容）
- 不在后台启动 uvicorn/QMT；联调真实 `xtdata` 时由用户本机手动启动 miniQMT

---

## 实施顺序小结

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14

每 Task 严格：**失败测试 → 实现 → 绿灯 → commit**。
