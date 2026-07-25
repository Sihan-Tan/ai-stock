# 尾盘选股 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仿造晨会，新增「尾盘选股」：对标记 `closing` 的策略，在 `SecurityMeta` 在市宇宙上只评买入信号，落库 + 飞书 + 页面重跑/历史/进自选；不下单。

**Architecture:** 独立包 `desk_closing_pick`（镜像 `desk_morning_brief`）。信号求值复用 `StrategyRegistry.load` + 与 `PaperStrategyRunner` 相同的日线 `load_daily_df` / `build_bar_row` / `on_bar` 路径，但只收集 `Side.BUY`、不调用 Broker。定时 job `run_closing_pick`（默认 14:40）与 API/页面共用 `ClosingPickService.run`。

**Tech Stack:** FastAPI、SQLAlchemy、`desk_strategy` / `desk_market` / `desk_alert`、APScheduler、pytest、React + HeroUI

**规格：** `docs/superpowers/specs/2026-07-25-closing-pick-design.md`

**Bar 口径（锁定）：** 与纸交易 Runner 一致——`MarketService.load_daily_df` 的**最后一根日 K** 作为求值 bar；`meta_json` 写入 `bar_date`（该行日期）。14:40 若库中尚无当日日线，则用上一交易日收盘 bar（可接受的首版局限）。

---

## 文件结构

| 路径 | 职责 |
| ---- | ---- |
| `packages/db/desk_db/models.py` | `ClosingBriefRow`、`ClosingPick` ORM |
| `packages/common/desk_common/contracts.py` | `ClosingBrief`、`ClosingPickReport` |
| `packages/closing_pick/desk_closing_pick/screen.py` | 单策略×单标的 buy 信号求值 |
| `packages/closing_pick/desk_closing_pick/__init__.py` | `ClosingPickService` |
| `packages/closing_pick/desk_closing_pick/bind.py` | 命中股进自选 |
| `packages/strategy/desk_strategy/__init__.py` | `merge_params` / `set_closing_role`（写 `params.roles`） |
| `apps/api/app/routes/closing.py` | `/api/closing/*` |
| `apps/api/app/routes/__init__.py` | 注册 router |
| `packages/market/desk_market/jobs.py` | `run_closing_pick` |
| `packages/market/desk_market/scheduler.py` | 注册 job |
| `configs/market/sync.yaml` | cron `40 14 * * 1-5` |
| `apps/web/src/pages/Closing.tsx` | 尾盘页 |
| `apps/web/src/layout/nav.ts`、`App.tsx`、`nav.test.ts` | 导航/路由 |
| `apps/web/src/pages/Strategies.tsx` | 「用于尾盘」勾选 |
| `apps/web/src/pages/MarketSync.tsx` | job 中文名 |
| `pyproject.toml`、`tests/conftest.py` | 包路径 |
| `tests/test_closing_pick.py` | 服务/扫股/bind |
| `tests/test_closing_api.py` | API 烟测 |
| `tests/test_market_pipeline_scheduler.py` | 断言新 job id |

---

### Task 1: ORM + contracts + 包骨架

**Files:**
- Modify: `packages/db/desk_db/models.py`（在 `MorningStrongPick` 后追加）
- Modify: `packages/common/desk_common/contracts.py`
- Create: `packages/closing_pick/desk_closing_pick/__init__.py`（可先空服务占位）
- Modify: `pyproject.toml`（`where` / packages 列表加 `packages/closing_pick`）
- Modify: `tests/conftest.py`（`sys.path` 加 closing_pick）

- [ ] **Step 1: 追加 ORM**

在 `MorningStrongPick` 类后增加：

```python
class ClosingBriefRow(Base):
    """尾盘选股文案。"""

    __tablename__ = "closing_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    stage: Mapped[str] = mapped_column(String(16), default="closing")
    content: Mapped[str] = mapped_column(Text)
    extras_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClosingPick(Base):
    """尾盘选股命中明细（按策略分行）。"""

    __tablename__ = "closing_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    pick_type: Mapped[str] = mapped_column(String(16), default="stock")
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[float] = mapped_column(Float, default=1.0)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
```

- [ ] **Step 2: 追加 contracts**

```python
class ClosingBrief(BaseModel):
    """尾盘选股报告。"""

    asof: date
    stage: Literal["closing"] = "closing"
    content: str
    extras: dict[str, Any] = Field(default_factory=dict)


class ClosingPickReport(BaseModel):
    """尾盘选股运行结果。"""

    asof: date
    strategy_ids: list[str] = Field(default_factory=list)
    stocks: list[dict[str, Any]] = Field(default_factory=list)
    content: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 3: 包占位 + 路径**

`packages/closing_pick/desk_closing_pick/__init__.py`：

```python
"""尾盘选股：策略 buy 信号扫证券宇宙。"""

from __future__ import annotations

# ClosingPickService 在 Task 3 实现
```

`pyproject.toml` 的 setuptools `where` 与 packages 列表加入 `"packages/closing_pick"`（与 `morning_brief` 并列）。

`tests/conftest.py` 的 `paths` 追加 `ROOT / "packages" / "closing_pick"`。

- [ ] **Step 4: 确认 create_all 含新表**

```bash
pytest tests/test_core.py::test_health -v
```

Expected: PASS（`Base.metadata.create_all` 会建新表，无导入错误）

- [ ] **Step 5: Commit**

```bash
git add packages/db/desk_db/models.py packages/common/desk_common/contracts.py packages/closing_pick pyproject.toml tests/conftest.py
git commit -m "feat(closing): 尾盘选股 ORM 与 contracts 骨架"
```

---

### Task 2: `screen.eval_buy` — 单标的 buy 求值

**Files:**
- Create: `packages/closing_pick/desk_closing_pick/screen.py`
- Create: `tests/test_closing_pick.py`

- [ ] **Step 1: 写失败测试**

```python
"""尾盘选股：扫股与落库。"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import SecurityMeta, StrategyRow
from desk_market import MarketService
from desk_closing_pick.screen import eval_buy_signals


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    yield Session(bind=get_engine())
    reset_engine()
    get_settings.cache_clear()


def _seed_bars(db: Session, symbol: str, n: int = 60, trend: float = 1.01):
    svc = MarketService(db)
    today = date.today()
    price = 10.0
    rows = []
    for i in range(n, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        price *= trend
        rows.append(
            {
                "date": d,
                "open": price * 0.99,
                "high": price * 1.01,
                "low": price * 0.98,
                "close": price,
                "volume": 1e6,
                "amount": price * 1e6,
                "open_hfq": price * 0.99,
                "high_hfq": price * 1.01,
                "low_hfq": price * 0.98,
                "close_hfq": price,
                "volume_hfq": 1e6,
            }
        )
    svc.upsert_daily_bars(symbol, pd.DataFrame(rows))
    db.commit()


def _seed_factor_yaml(db: Session, strategy_id: str, yaml_body: str, roles: list[str] | None = None):
    params = {"roles": roles or []}
    db.add(
        StrategyRow(
            strategy_id=strategy_id,
            name=strategy_id,
            source="yaml",
            version="v0.1",
            status="research",
            lifecycle_stage="incubating",
            yaml_body=yaml_body,
            params_json=json.dumps(params, ensure_ascii=False),
        )
    )
    db.commit()


ALWAYS_BUY_YAML = """
id: close_always_buy
name: always buy close gt 0
kind: factor_rules
buy:
  mode: all
  conditions:
    - left: { factor: CLOSE }
      op: gt
      right: { value: 0 }
sell:
  mode: all
  conditions: []
"""


def test_eval_buy_signals_returns_buy(db: Session):
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])
    out = eval_buy_signals(db, strategy_id="close_always_buy", symbol="600519.SH")
    assert out["ok"] is True
    assert len(out["signals"]) >= 1
    assert out["bar_date"] is not None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_closing_pick.py::test_eval_buy_signals_returns_buy -v
```

Expected: FAIL（`ModuleNotFoundError` 或 import error）

- [ ] **Step 3: 实现 `screen.py`**

```python
"""单策略 × 单标的买入信号求值（不下单）。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import yaml
from sqlalchemy.orm import Session

from desk_common.contracts import Side
from desk_market import MarketService
from desk_strategy import StrategyRegistry
from desk_strategy.bar_context import build_bar_row
from desk_strategy.factor_rules import attach_ml_factor_columns, collect_factor_names


def eval_buy_signals(
    db: Session, *, strategy_id: str, symbol: str
) -> dict[str, Any]:
    """
    评估最新日 K 的买入信号。

    @returns: ok / signals / bar_date / last_close / message / pct_chg
    """
    base: dict[str, Any] = {
        "ok": False,
        "signals": [],
        "bar_date": None,
        "last_close": None,
        "pct_chg": None,
        "message": "",
    }
    reg = StrategyRegistry(db).load(strategy_id)
    if not reg or not reg.on_bar:
        base["message"] = f"strategy not runnable: {strategy_id}"
        return base

    end = date.today()
    start = end - timedelta(days=400)
    df = MarketService(db).load_daily_df(symbol, start, end)
    if df is None or getattr(df, "empty", True) or len(df) < 30:
        base["message"] = "insufficient bars"
        return base

    history = df.copy()
    body = getattr(reg.meta, "yaml_body", None) or ""
    parsed = yaml.safe_load(body) if body else None
    if isinstance(parsed, dict):
        history = attach_ml_factor_columns(
            history, collect_factor_names(parsed), db
        )

    idx = len(df) - 1
    lookback = min(250, idx + 1)
    slice_df = df.iloc[idx + 1 - lookback : idx + 1]
    row = build_bar_row(
        symbol,
        closes=slice_df["close"].astype(float).tolist(),
        highs=slice_df["high"].astype(float).tolist(),
        lows=slice_df["low"].astype(float).tolist(),
        opens=slice_df["open"].astype(float).tolist(),
        volumes=slice_df["volume"].astype(float).tolist(),
    )
    signals = reg.on_bar({"row": row, "history": history, "db": db}) or []
    buys = []
    for s in signals:
        side = s.side if hasattr(s, "side") else Side(str(s.get("side")))
        if side == Side.BUY:
            buys.append(s.model_dump() if hasattr(s, "model_dump") else dict(s))

    last = df.iloc[-1]
    prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
    last_close = float(last["close"])
    pct = (last_close / prev_close - 1.0) if prev_close else 0.0
    bar_date = last["date"] if "date" in df.columns else None
    if hasattr(bar_date, "date"):
        bar_date = bar_date.date()
    elif hasattr(bar_date, "isoformat"):
        pass
    else:
        bar_date = None

    base.update(
        {
            "ok": True,
            "signals": buys,
            "bar_date": bar_date.isoformat() if bar_date else None,
            "last_close": last_close,
            "pct_chg": round(pct, 6),
            "message": "",
        }
    )
    return base
```

（若 `load_daily_df` 的 date 在 index 上，按现有 `MarketService` 实际列调整 `bar_date` 读取，与 `paper_runner` / 测试数据一致即可。）

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_closing_pick.py::test_eval_buy_signals_returns_buy -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/closing_pick/desk_closing_pick/screen.py tests/test_closing_pick.py
git commit -m "feat(closing): 单标的 buy 信号求值 screen.eval_buy_signals"
```

---

### Task 3: `ClosingPickService` + roles 过滤 + 落库/飞书

**Files:**
- Modify: `packages/closing_pick/desk_closing_pick/__init__.py`
- Modify: `packages/strategy/desk_strategy/__init__.py`（增加 `set_closing_role` / `list_closing_candidates`）
- Modify: `tests/test_closing_pick.py`

- [ ] **Step 1: 追加失败测试**

```python
from desk_closing_pick import ClosingPickService
from desk_db.models import ClosingPick, ClosingBriefRow
from sqlalchemy import select


def test_run_scans_universe_and_stores_picks(db: Session):
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.add(SecurityMeta(symbol="000001.SZ", name="平安", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH", trend=1.01)
    _seed_bars(db, "000001.SZ", trend=1.01)
    _seed_factor_yaml(db, "close_always_buy", ALWAYS_BUY_YAML, roles=["closing"])

    report = ClosingPickService(db).run(asof=date.today())
    assert "close_always_buy" in report.strategy_ids
    assert len(report.stocks) >= 1
    picks = db.scalars(select(ClosingPick).where(ClosingPick.asof == date.today())).all()
    assert len(picks) >= 1
    briefs = db.scalars(select(ClosingBriefRow).where(ClosingBriefRow.asof == date.today())).all()
    assert len(briefs) >= 1


def test_run_skips_strategies_without_closing_role(db: Session):
    db.add(SecurityMeta(symbol="600519.SH", name="茅台", is_delisted=False, status="listed"))
    db.commit()
    _seed_bars(db, "600519.SH")
    _seed_factor_yaml(db, "no_role", ALWAYS_BUY_YAML.replace("close_always_buy", "no_role"), roles=[])
    report = ClosingPickService(db).run(asof=date.today())
    assert report.strategy_ids == []
    assert report.stocks == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_closing_pick.py::test_run_scans_universe_and_stores_picks -v
```

Expected: FAIL

- [ ] **Step 3: 实现 Service**

`StrategyRegistry` 增加（或放在 closing 包内纯函数亦可；推荐 Registry 以便 API 复用）：

```python
def strategy_has_closing_role(params: dict) -> bool:
    roles = params.get("roles") or []
    return isinstance(roles, list) and "closing" in roles


def set_closing_role(self, strategy_id: str, enabled: bool) -> StrategyMeta | None:
    row = self._latest_row(strategy_id)  # 使用现有取最新版本行的私有/公开方法
    if not row:
        return None
    params = json.loads(row.params_json or "{}")
    roles = list(params.get("roles") or [])
    if enabled and "closing" not in roles:
        roles.append("closing")
    if not enabled:
        roles = [r for r in roles if r != "closing"]
    params["roles"] = roles
    row.params_json = json.dumps(params, ensure_ascii=False)
    self.db.flush()
    return self.get_meta(strategy_id)
```

（实现时对齐现有 `_latest_row` / `get_meta` 命名；若无私有方法则 `select(StrategyRow).where(...).order_by(id.desc())`。）

`ClosingPickService` 核心逻辑：

```python
class ClosingPickService:
    def __init__(self, db: Session):
        self.db = db
        self.calendar = CalendarService(db)
        self.alert = FeishuWebhookChannel(db)

    def list_closing_strategy_ids(self) -> list[str]:
        # 扫 StrategyRow 最新版本，params.roles 含 closing，排除 archived/retired
        ...

    def listed_universe(self) -> list[tuple[str, str]]:
        rows = self.db.scalars(
            select(SecurityMeta).where(SecurityMeta.is_delisted.is_(False))
        ).all()
        return [(r.symbol, r.name or "") for r in rows]

    def run(
        self,
        asof: date | None = None,
        strategy_ids: list[str] | None = None,
    ) -> ClosingPickReport:
        asof = asof or date.today()
        if not self.calendar.is_trade_day(asof):
            content = f"{asof} 非交易日，跳过尾盘选股。"
            self._store_brief(asof, content, {})
            return ClosingPickReport(asof=asof, content=content)

        ids = strategy_ids or self.list_closing_strategy_ids()
        # 若显式传入，仍可跑未打标策略（页面勾选重跑）
        universe = self.listed_universe()
        stocks: list[dict] = []

        # 清理旧 picks
        q = select(ClosingPick).where(ClosingPick.asof == asof)
        if strategy_ids:
            q = q.where(ClosingPick.strategy_id.in_(ids))
        for old in self.db.scalars(q).all():
            self.db.delete(old)

        for sid in ids:
            for symbol, name in universe:
                ev = eval_buy_signals(self.db, strategy_id=sid, symbol=symbol)
                if not ev.get("ok") or not ev.get("signals"):
                    continue
                pct = float(ev.get("pct_chg") or 0)
                score = round(pct * 100, 2)
                meta = {
                    "symbol": symbol,
                    "name": name,
                    "strategy_id": sid,
                    "bar_date": ev.get("bar_date"),
                    "pct_chg": pct,
                    "last_close": ev.get("last_close"),
                    "signals": ev.get("signals"),
                }
                self.db.add(
                    ClosingPick(
                        asof=asof,
                        strategy_id=sid,
                        pick_type="stock",
                        code=symbol,
                        name=name,
                        score=score,
                        meta_json=json.dumps(meta, ensure_ascii=False),
                    )
                )
                stocks.append(meta)

        stocks.sort(key=lambda x: x.get("pct_chg") or 0, reverse=True)
        bits = [f"{s['symbol']}({s.get('strategy_id')})" for s in stocks[:6]]
        content = (
            f"【尾盘选股】{asof}\n"
            f"策略 {len(ids)} 个 · 命中 {len(stocks)} 只\n"
            f"{' · '.join(bits) if bits else '无命中'}"
        )
        extras = {"strategy_ids": ids, "hit_count": len(stocks)}
        self._store_brief(asof, content, extras)
        self.alert.send(
            "尾盘选股",
            content,
            category="closing",
            dedupe_key=f"closing:{asof}",
        )
        self.db.flush()
        return ClosingPickReport(
            asof=asof, strategy_ids=ids, stocks=stocks, content=content
        )
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/test_closing_pick.py -v
```

Expected: PASS（飞书未配置时应不抛错，与晨会一致）

- [ ] **Step 5: Commit**

```bash
git add packages/closing_pick packages/strategy/desk_strategy/__init__.py tests/test_closing_pick.py
git commit -m "feat(closing): ClosingPickService 扫宇宙落库并推送飞书"
```

---

### Task 4: bind + API 路由

**Files:**
- Create: `packages/closing_pick/desk_closing_pick/bind.py`
- Create: `apps/api/app/routes/closing.py`
- Modify: `apps/api/app/routes/__init__.py`
- Create: `tests/test_closing_api.py`
- Modify: `tests/test_closing_pick.py`（bind 单测）

- [ ] **Step 1: bind 实现（对标 `bind_morning_picks`）**

```python
def bind_closing_picks(
    db: Session,
    *,
    asof: date | None = None,
    limit: int = 20,
    symbols: list[str] | None = None,
    strategy_ids: list[str] | None = None,
) -> dict[str, Any]:
    ...
```

按 `score` 降序；可选 `strategy_ids` 过滤；去重 symbol 后再 `MarketService.add_watchlist`。

- [ ] **Step 2: API**

`apps/api/app/routes/closing.py`：

| 端点 | 行为 |
| ---- | ---- |
| `POST /run` | `ClosingPickService(db).run(asof, strategy_ids)` |
| `GET /latest` | 同晨会 latest：brief + stocks（含 strategy_id） |
| `GET /history?asof=` | 与 latest 相同，`asof` 必填（或默认 today） |
| `POST /bind` | `bind_closing_picks` |
| `GET /strategies` | 全部非 archived 策略 + `closing: bool` |
| `POST /strategies/mark` | body `{strategy_id, closing: bool}` → `set_closing_role` |

注册：`api_router.include_router(closing.router, tags=["closing"])`。

- [ ] **Step 3: API 测试**

```python
def test_closing_run_and_latest(client, ...):
    # seed SecurityMeta + bars + yaml with roles
    r = client.post("/api/closing/run", json={})
    assert r.status_code == 200
    latest = client.get("/api/closing/latest")
    assert latest.status_code == 200
    assert "briefs" in latest.json() or "content" in latest.json()
```

（响应形状与 `morning_latest` 对齐更佳：`{asof, briefs, stocks}`。）

- [ ] **Step 4: 跑测并 Commit**

```bash
pytest tests/test_closing_pick.py tests/test_closing_api.py -v
git add packages/closing_pick apps/api/app/routes tests/test_closing_api.py
git commit -m "feat(closing): 尾盘选股 API 与 bind 自选"
```

---

### Task 5: 定时 Job + sync.yaml + MarketSync 文案

**Files:**
- Modify: `packages/market/desk_market/jobs.py`
- Modify: `packages/market/desk_market/scheduler.py`
- Modify: `configs/market/sync.yaml`
- Modify: `tests/test_market_pipeline_scheduler.py`
- Modify: `apps/web/src/pages/MarketSync.tsx`

- [ ] **Step 1: Job 方法**

```python
def run_closing_pick(self, asof: date | None = None, *, run_id: int | None = None) -> dict[str, Any]:
    from desk_closing_pick import ClosingPickService

    row = self._begin("run_closing_pick", run_id)
    try:
        asof = asof or date.today()
        if not CalendarService(self.db).require_trade_day(asof):
            self.store.finish(row, status="ok", message="skipped_non_trade_day")
            return {"status": "ok", "skipped": True, "run_id": row.id}
        report = ClosingPickService(self.db).run(asof)
        self.store.finish(
            row, status="ok", symbols_done=len(report.stocks), message=report.content[:200]
        )
        return {"status": "ok", "report": report.model_dump(), "run_id": row.id}
    except Exception as exc:
        self.store.finish(row, status="failed", error_summary=str(exc))
        return {"status": "failed", "error": str(exc), "run_id": row.id}
```

- [ ] **Step 2: scheduler + yaml**

`scheduler.py`：`_add("run_closing_pick", "run_closing_pick")`

`sync.yaml`：

```yaml
run_closing_pick: { cron: "40 14 * * 1-5" }
```

- [ ] **Step 3: 测试 expected job ids 加入 `run_closing_pick`**

```bash
pytest tests/test_market_pipeline_scheduler.py -v
```

- [ ] **Step 4: MarketSync `JOB_LABELS`**

`run_closing_pick: "尾盘选股"`

确认手动触发 jobs 列表若写死 job id，一并加入（搜 `run_morning` 同文件模式）。

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(closing): 注册尾盘选股定时任务 14:40"
```

---

### Task 6: 前端 Closing 页 + 导航

**Files:**
- Create: `apps/web/src/pages/Closing.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/layout/nav.ts`
- Modify: `apps/web/src/layout/nav.test.ts`

- [ ] **Step 1: 导航**

在「晨会」后插入 `{ path: "/closing", label: "尾盘选股" }`；更新 `nav.test.ts` 断言。

- [ ] **Step 2: `Closing.tsx`（对标 Morning）**

功能：

- `GET /api/closing/latest` 展示文案 + 个股表（列：代码、名称、策略、涨跌幅、score）
- `GET /api/closing/strategies` 多选 checkbox（默认勾选 `closing: true`）
- 按钮：刷新 / 立即跑（`POST /run` body `{ strategy_ids }`）/ 进自选（`POST /bind`）
- 点击代码打开 `StockDetailDrawer`（同晨会）
- JSDoc 注释组件与主要 handler

- [ ] **Step 3: App 路由**

```tsx
<Route path="/closing" element={<Closing setLog={setLog} />} />
```

- [ ] **Step 4: 前端类型检查（若有）**

```bash
cd apps/web && npx tsc --noEmit
```

或项目既有 web test：`npm test -- nav.test`（以仓库脚本为准）。

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(closing): 尾盘选股前端页与导航"
```

---

### Task 7: 策略列表「用于尾盘」勾选

**Files:**
- Modify: `apps/web/src/pages/Strategies.tsx`
- （可选）`Strategy` 类型增加 `params?: { roles?: string[] }`——确认 `list` API 的 `model_dump` 已含 `params`

- [ ] **Step 1: 列表行增加 Checkbox**

文案：「尾盘」。`onChange` →

```ts
await api(`/api/closing/strategies/mark`, {
  method: "POST",
  body: JSON.stringify({ strategy_id: row.id, closing: checked }),
});
await load();
```

- [ ] **Step 2: 手动/单测不强制**；确认 `GET /api/strategies` 返回 `params.roles`

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(closing): 策略列表可标记用于尾盘选股"
```

---

### Task 8: 规格状态 + 总验收

**Files:**
- Modify: `docs/superpowers/specs/2026-07-25-closing-pick-design.md`（状态 → 已实现）

- [ ] **Step 1: 跑相关测试**

```bash
pytest tests/test_closing_pick.py tests/test_closing_api.py tests/test_market_pipeline_scheduler.py tests/test_core.py::test_health -v
```

Expected: 全部 PASS

- [ ] **Step 2: 对照成功标准自检**

1. 标 `closing` 后 `POST /run` 有 picks 或「0 命中」文案  
2. job id 已注册  
3. 页面可展示 + bind  
4. 飞书 category=closing（无 webhook 时不炸）  
5. 无 paper/live 订单路径被调用  

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: 标记尾盘选股设计为已实现"
```

---

## Spec 覆盖自检

| 规格项 | Task |
| ------ | ---- |
| 独立包镜像晨会 | 1, 3 |
| roles=`closing` 多策略 | 3, 4, 7 |
| SecurityMeta 宇宙 | 3 |
| 只评 buy、不下单 | 2, 3 |
| brief/picks 表 | 1, 3 |
| API run/latest/history/bind/strategies | 4 |
| 定时 14:40 | 5 |
| 飞书 category=closing | 3 |
| 前端页 + 导航 | 6 |
| 策略勾选 | 7 |
| Bar 口径锁定 | Task 2 注释 + 上文 |

无 TBD 占位；history 与 latest 同形，避免两套逻辑。
