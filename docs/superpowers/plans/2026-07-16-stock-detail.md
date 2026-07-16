# 股票详情页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现抽屉 + 全页股票详情：行情头、分时/日/周/月 K、基本信息、行业/概念、资金面、技术面；入口为持仓、自选与壳层搜索。

**Architecture:** 前端共用 `StockDetailView`；全页路由 `/stock/:symbol`，监控/自选用抽屉并可展开。复用已有 quote/bars；新增按标的 meta、boards、capital-flow、technicals。库表优先，缺口 live（AkShare/xtdata）后可选落库；单模块失败返回 `available: false`，不炸整页。周/月 K 由日线聚合（后端提供 `period=week|month` 或前端聚合日线，本计划用后端聚合接口保持契约稳定）。

**Tech Stack:** FastAPI、SQLAlchemy、pandas、`desk_indicators`、AkShare（可 Mock）、Vite + React 19 + HeroUI、`lightweight-charts`、pytest、vitest。

**Spec:** `docs/superpowers/specs/2026-07-16-stock-detail-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `packages/db/desk_db/models.py` | 新增 `CapitalFlowDaily`（可选落库） |
| `packages/market/desk_market/stock_detail.py` | meta / boards-by-symbol / capital / technicals / 日线聚合周月 |
| `packages/market/desk_market/akshare_capital.py` | AkShare 个股资金流客户端（可注入 Mock） |
| `apps/api/app/routes/market.py` | 注册 stock 相关 GET 路由 |
| `tests/test_stock_detail_api.py` | API 契约与空态 |
| `tests/test_stock_detail_aggregate.py` | 日→周/月聚合 |
| `apps/web/package.json` | 增加 `lightweight-charts` |
| `apps/web/src/stock/types.ts` | 详情相关 TS 类型 |
| `apps/web/src/stock/StockChart.tsx` | K 线 / 分时图 |
| `apps/web/src/stock/StockDetailView.tsx` | 共用详情内容 |
| `apps/web/src/stock/StockDetailDrawer.tsx` | 右侧抽屉壳 |
| `apps/web/src/pages/StockDetail.tsx` | 全页路由页 |
| `apps/web/src/App.tsx` | 注册 `/stock/:symbol`（须在 `*` 之前） |
| `apps/web/src/layout/AppShell.tsx` | 顶部搜索跳转全页 |
| `apps/web/src/pages/Paper.tsx` | 持仓行点击开抽屉 |
| `apps/web/src/pages/Watchlist.tsx` | 自选行点击开抽屉 |
| `apps/web/src/stock/positionContext.ts` | 仓位摘要类型与格式化 |
| `apps/web/src/stock/stockDetailApi.test.ts` | 纯函数/路径辅助单测（可选） |

**不做（本计划外）：** WebSocket、分钟多周期 K、板块详情路由、单一 overview 大接口。

---

### Task 1: CapitalFlowDaily 模型 + 日线周/月聚合纯函数

**Files:**
- Modify: `packages/db/desk_db/models.py`
- Create: `packages/market/desk_market/stock_detail.py`（先放聚合与类型）
- Test: `tests/test_stock_detail_aggregate.py`

- [ ] **Step 1: Write the failing test**

```python
"""日线聚合为周/月 K。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from desk_market.stock_detail import aggregate_ohlcv


def test_aggregate_week_and_month():
    rows = [
        {"date": date(2024, 1, 2), "open": 10, "high": 11, "low": 9.5, "close": 10.5, "volume": 100, "amount": 1000},
        {"date": date(2024, 1, 3), "open": 10.5, "high": 12, "low": 10, "close": 11, "volume": 200, "amount": 2200},
        {"date": date(2024, 1, 8), "open": 11, "high": 11.5, "low": 10.8, "close": 11.2, "volume": 150, "amount": 1650},
    ]
    df = pd.DataFrame(rows)
    week = aggregate_ohlcv(df, "week")
    assert len(week) >= 2
    assert week.iloc[0]["open"] == 10
    assert week.iloc[0]["close"] == 11
    assert week.iloc[0]["high"] == 12
    assert week.iloc[0]["volume"] == 300

    month = aggregate_ohlcv(df, "month")
    assert len(month) == 1
    assert month.iloc[0]["close"] == 11.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stock_detail_aggregate.py -v`  
Expected: FAIL（`stock_detail` / `aggregate_ohlcv` 未定义）

- [ ] **Step 3: Implement model + aggregate**

在 `models.py` 的 `BoardMember` 附近新增：

```python
class CapitalFlowDaily(Base):
    """个股资金流向日频（可选落库）。"""

    __tablename__ = "capital_flow_daily"
    __table_args__ = (UniqueConstraint("symbol", "ts", name="uq_capital_flow_daily_symbol_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[date] = mapped_column(Date, index=True)
    main_net: Mapped[float] = mapped_column(Float, default=0.0)
    super_net: Mapped[float] = mapped_column(Float, default=0.0)
    large_net: Mapped[float] = mapped_column(Float, default=0.0)
    medium_net: Mapped[float] = mapped_column(Float, default=0.0)
    small_net: Mapped[float] = mapped_column(Float, default=0.0)
```

`packages/market/desk_market/stock_detail.py`：

```python
"""单标的详情：聚合、meta、板块、资金、技术面。"""

from __future__ import annotations

import pandas as pd


def aggregate_ohlcv(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """
    将日线 OHLCV 聚合为周/月。

    @param df: 需含 date/open/high/low/close/volume/amount
    @param period: week | month
    """
    if df.empty:
        return df.copy()
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date")
    freq = "W-FRI" if period == "week" else "ME"
    grouped = out.set_index("date").resample(freq)
    agg = grouped.agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        }
    ).dropna(subset=["open"])
    agg = agg.reset_index()
    agg["date"] = agg["date"].dt.date
    return agg
```

说明：SQLite 测试走 `Base.metadata.create_all`，无需本任务强制 Alembic；若团队对生产库有迁移惯例，可另开 `alembic/versions/..._capital_flow_daily.py`（可选 Step）。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stock_detail_aggregate.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/db/desk_db/models.py packages/market/desk_market/stock_detail.py tests/test_stock_detail_aggregate.py
git commit -m "feat(market): add capital-flow model and OHLCV week/month aggregate"
```

---

### Task 2: Meta + 所属板块读接口

**Files:**
- Modify: `packages/market/desk_market/stock_detail.py`
- Modify: `packages/market/desk_market/__init__.py`（如需 re-export）
- Modify: `apps/api/app/routes/market.py`
- Test: `tests/test_stock_detail_api.py`

- [ ] **Step 1: Write the failing tests**

```python
"""股票详情相关 API。"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine, get_session_factory
import desk_db.models  # noqa: F401
from desk_db.models import BoardMember, SecurityMeta


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def client(_db):
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_security_meta_and_boards_for_symbol(client, _db):
    db = get_session_factory()()
    db.add(SecurityMeta(symbol="600519.SH", name="贵州茅台", status="listed"))
    db.add(
        BoardMember(
            board_code="BK0001",
            board_name="白酒",
            board_type="sector",
            symbol="600519.SH",
            effective_from=date(2020, 1, 1),
        )
    )
    db.commit()
    db.close()

    r = client.get("/api/market/stock/600519.SH/meta")
    assert r.status_code == 200
    assert r.json()["name"] == "贵州茅台"

    b = client.get("/api/market/stock/600519.SH/boards")
    assert b.status_code == 200
    assert b.json()["boards"][0]["board_name"] == "白酒"

    missing = client.get("/api/market/stock/999999.SH/meta")
    assert missing.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stock_detail_api.py::test_security_meta_and_boards_for_symbol -v`  
Expected: FAIL（404 / 路由不存在）

- [ ] **Step 3: Implement service + routes**

在 `stock_detail.py` 增加（用 `Session`、`normalize_symbol`、`select`）：

```python
def get_security_meta(db: Session, symbol: str) -> dict | None:
    sym = normalize_symbol(symbol)
    row = db.scalar(select(SecurityMeta).where(SecurityMeta.symbol == sym))
    if row is None:
        return None
    return {
        "symbol": row.symbol,
        "name": row.name,
        "is_delisted": row.is_delisted,
        "status": row.status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_boards_for_symbol(db: Session, symbol: str) -> list[dict]:
    sym = normalize_symbol(symbol)
    rows = db.scalars(
        select(BoardMember).where(
            BoardMember.symbol == sym,
            BoardMember.effective_to.is_(None),
        )
    ).all()
    return [
        {
            "board_code": r.board_code,
            "board_name": r.board_name,
            "board_type": r.board_type,
        }
        for r in rows
    ]
```

在 `market.py`：

```python
@router.get("/stock/{symbol}/meta")
def stock_meta(symbol: str, db: Session = Depends(get_db)):
    from desk_market.stock_detail import get_security_meta
    data = get_security_meta(db, symbol)
    if data is None:
        raise HTTPException(status_code=404, detail="symbol not found")
    return data


@router.get("/stock/{symbol}/boards")
def stock_boards(symbol: str, db: Session = Depends(get_db)):
    from desk_market.stock_detail import list_boards_for_symbol
    return {"symbol": symbol, "boards": list_boards_for_symbol(db, symbol)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stock_detail_api.py::test_security_meta_and_boards_for_symbol -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/market/desk_market/stock_detail.py apps/api/app/routes/market.py tests/test_stock_detail_api.py
git commit -m "feat(api): add stock meta and boards-by-symbol endpoints"
```

---

### Task 3: bars 支持 period=day|week|month + technicals API

**Files:**
- Modify: `packages/market/desk_market/stock_detail.py`
- Modify: `apps/api/app/routes/market.py`
- Test: `tests/test_stock_detail_api.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_bars_daily_period_week(client, _db):
    from desk_market import MarketService
    from desk_db import get_session_factory
    import pandas as pd

    db = get_session_factory()()
    svc = MarketService(db)
    # 写入至少两周日线（沿用项目既有 upsert_daily_bars / seed 方式）
    # ... seed 600519.SH 10 个交易日 ...
    db.commit()
    db.close()

    r = client.get(
        "/api/market/bars/daily",
        params={"symbol": "600519.SH", "from": "2024-01-01", "to": "2024-01-31", "period": "week"},
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) < 10  # 周线根数应少于日线


def test_technicals_available(client, _db, monkeypatch):
    # seed 足够日线后
    r = client.get("/api/market/stock/600519.SH/technicals")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert "ma5" in body["latest"]
    assert "macd" in body["latest"]
    assert "rsi14" in body["latest"]
```

实现时按仓库现有 `MarketService.upsert_daily_bars` / `seed` 习惯填满 seed；若 upsert 签名不同，以 `tests/test_market_pipeline_upsert.py` 为准抄写入方式。

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stock_detail_api.py::test_bars_daily_period_week tests/test_stock_detail_api.py::test_technicals_available -v`  
Expected: FAIL

- [ ] **Step 3: Implement**

扩展 `bars_daily`：增加可选 `period: str | None = Query(None)`；当 `period in ("week","month")` 时对 `load_daily_df` 结果调用 `aggregate_ohlcv` 再 `to_dict`。

`compute_technicals(db, symbol, lookback_days=180)`：

```python
from desk_indicators import compute

def compute_technicals(db: Session, symbol: str, *, lookback_days: int = 180) -> dict:
    sym = normalize_symbol(symbol)
    to = date.today()
    fr = to - timedelta(days=lookback_days)
    df = MarketService(db).load_daily_df(sym, fr, to, adj=None)
    if df is None or df.empty or len(df) < 30:
        return {"available": False, "error": "insufficient bars", "symbol": sym}
    # 统一列名 date
    work = df.rename(columns={"date": "date"}) if "date" in df.columns else df.copy()
    if "date" not in work.columns and "ts" in work.columns:
        work = work.rename(columns={"ts": "date"})
    ind = compute(work, ["SMA_5", "SMA_10", "SMA_20", "RSI_14", "MACD"])
    last = ind.iloc[-1]
    series = []
    for _, row in ind.iterrows():
        series.append({
            "date": str(row["date"])[:10] if "date" in row else None,
            "ma5": _f(row.get("sma_5")),
            "ma10": _f(row.get("sma_10")),
            "ma20": _f(row.get("sma_20")),
            "macd": _f(row.get("macd")),
            "macd_signal": _f(row.get("macd_signal")),
            "macd_hist": _f(row.get("macd_hist")),
            "rsi14": _f(row.get("rsi_14")),
        })
    return {
        "available": True,
        "symbol": sym,
        "source": "db",
        "as_of": str(last.get("date", ""))[:10],
        "latest": {
            "ma5": _f(last.get("sma_5")),
            "ma10": _f(last.get("sma_10")),
            "ma20": _f(last.get("sma_20")),
            "macd": _f(last.get("macd")),
            "macd_signal": _f(last.get("macd_signal")),
            "macd_hist": _f(last.get("macd_hist")),
            "rsi14": _f(last.get("rsi_14")),
        },
        "series": series,
    }
```

路由：

```python
@router.get("/stock/{symbol}/technicals")
def stock_technicals(symbol: str, db: Session = Depends(get_db)):
    from desk_market.stock_detail import compute_technicals
    try:
        return compute_technicals(db, symbol)
    except Exception as exc:  # noqa: BLE001
        logger.exception("technicals failed %s", symbol)
        return {"available": False, "symbol": symbol, "error": str(exc)[:200]}
```

非法空 symbol 仍 404 可选；数据不足用 `available: false`。

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(api): week/month bars period and stock technicals"
```

---

### Task 4: capital-flow API（库优先 + AkShare live）

**Files:**
- Create: `packages/market/desk_market/akshare_capital.py`
- Modify: `packages/market/desk_market/stock_detail.py`
- Modify: `apps/api/app/routes/market.py`
- Test: `tests/test_stock_detail_api.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_capital_flow_from_db(client, _db):
    from desk_db.models import CapitalFlowDaily
    db = get_session_factory()()
    db.add(
        CapitalFlowDaily(
            symbol="600519.SH",
            ts=date.today(),
            main_net=1.2e8,
            super_net=5e7,
            large_net=3e7,
            medium_net=-1e7,
            small_net=-2e7,
        )
    )
    db.commit()
    db.close()
    r = client.get("/api/market/stock/600519.SH/capital-flow")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["source"] == "db"
    assert body["latest"]["main_net"] == 1.2e8


def test_capital_flow_live_fallback(client, _db, monkeypatch):
    from desk_market import akshare_capital as ac

    class Fake:
        def fetch_daily(self, symbol: str, days: int = 20):
            return [
                {
                    "ts": date.today(),
                    "main_net": 100.0,
                    "super_net": 10.0,
                    "large_net": 20.0,
                    "medium_net": 30.0,
                    "small_net": 40.0,
                }
            ]

    monkeypatch.setattr(
        "desk_market.stock_detail.get_capital_client",
        lambda: Fake(),
    )
    r = client.get("/api/market/stock/600519.SH/capital-flow")
    assert r.status_code == 200
    assert r.json()["available"] is True
    assert r.json()["source"] == "live"


def test_capital_flow_unavailable(client, _db, monkeypatch):
    class Boom:
        def fetch_daily(self, symbol: str, days: int = 20):
            raise RuntimeError("network")

    monkeypatch.setattr(
        "desk_market.stock_detail.get_capital_client",
        lambda: Boom(),
    )
    r = client.get("/api/market/stock/000001.SZ/capital-flow")
    assert r.status_code == 200
    assert r.json()["available"] is False
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement client + service + route**

`akshare_capital.py`：封装 `stock_individual_fund_flow`（或项目里已验证可用的等价接口）；映射列到 `main_net/super_net/...`；失败抛错。提供 `get_capital_client()` 默认单例便于 monkeypatch。

`get_capital_flow(db, symbol, days=20)`：

1. `normalize_symbol`；非法可 404（路由层）。
2. 查 `CapitalFlowDaily` 近 `days` 条；有则 `source=db`。
3. 否则 `client.fetch_daily`；成功则 upsert 落库，`source=live`。
4. 失败：`{"available": False, "error": "...", "symbol": sym}`。

路由 `GET /stock/{symbol}/capital-flow`：try/except 保证 200 + `available: false`。

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(api): stock capital-flow with db-first live fallback"
```

---

### Task 5: 前端依赖 + StockChart + types

**Files:**
- Modify: `apps/web/package.json`
- Create: `apps/web/src/stock/types.ts`
- Create: `apps/web/src/stock/StockChart.tsx`
- Create: `apps/web/src/stock/format.ts`（可选数字格式）

- [ ] **Step 1: Install**

```powershell
cd E:\study\AiMakeMoney\apps\web
npm install lightweight-charts
```

- [ ] **Step 2: Add types**

```typescript
/** 仓位摘要（仅从监控持仓带入） */
export type PositionContext = {
  symbol: string;
  qty: number;
  cost: number;
  last?: number;
  pnl?: number;
  pnlPct?: number;
  weightPct?: number;
};

export type ChartPeriod = "intraday" | "day" | "week" | "month";

export type OhlcvBar = {
  date?: string;
  ts?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
};
```

- [ ] **Step 3: Implement `StockChart`**

用 `lightweight-charts` 的 `createChart` + `CandlestickSeries`（日/周/月）或 `AreaSeries`/`LineSeries`（分时用 close）；`useEffect` 根据 `bars`/`period` 更新；组件卸载 `chart.remove()`。容器 `className="h-64 w-full"`（抽屉可 `h-48`）。

- [ ] **Step 4: Smoke**

Run: `cd apps/web && npm run build`  
Expected: 编译通过

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): add lightweight-charts StockChart for detail page"
```

---

### Task 6: StockDetailView + 全页路由

**Files:**
- Create: `apps/web/src/stock/StockDetailView.tsx`
- Create: `apps/web/src/pages/StockDetail.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/layout/nav.ts`（通常不加侧栏项；仅 title 解析）
- Modify: `apps/web/src/App.tsx` title `useMemo`：若 `pathname.startsWith("/stock/")` 则标题为「股票详情」或 decode symbol

- [ ] **Step 1: Implement `StockDetailView`**

Props：

```typescript
type Props = {
  symbol: string;
  position?: PositionContext | null;
  compact?: boolean; // 抽屉模式
  onExpand?: () => void;
  onClose?: () => void;
};
```

行为：

1. `useState` period 默认 `intraday`；`positionCollapsed` 默认 `false`（compact 下可默认展开摘要）。
2. `useEffect` 并行：  
   - `GET /api/market/intraday/quote?symbols=`  
   - `GET /api/market/stock/{symbol}/meta`（404 则 `notFound`）  
   - `GET /api/market/stock/{symbol}/boards`  
   - `GET /api/market/stock/{symbol}/capital-flow`  
   - `GET /api/market/stock/{symbol}/technicals`  
   - bars：分时 → `bars/minute`（当日交易时段）；日/周/月 → `bars/daily?period=`
3. 各区块独立 loading/error；`available === false` 显示空态文案。
4. 仓位条：仅 `position` 存在时渲染；按钮切换收起。
5. HeroUI：`Button`、`Chip`、`Tabs`（或手写 Tab）、`Spinner`、`Alert`。

- [ ] **Step 2: `StockDetail` page**

```tsx
import { useLocation, useParams } from "react-router-dom";
import { StockDetailView } from "../stock/StockDetailView";
import type { PositionContext } from "../stock/types";

export default function StockDetail() {
  const { symbol = "" } = useParams();
  const location = useLocation();
  const position = (location.state as { position?: PositionContext } | null)?.position ?? null;
  return (
    <StockDetailView
      symbol={decodeURIComponent(symbol).toUpperCase()}
      position={position}
    />
  );
}
```

- [ ] **Step 3: Register route BEFORE `*`**

```tsx
<Route path="/stock/:symbol" element={<StockDetail />} />
```

- [ ] **Step 4: Build**

Run: `cd apps/web && npm run build`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): add /stock/:symbol detail page with StockDetailView"
```

---

### Task 7: 抽屉 + 持仓/自选入口

**Files:**
- Create: `apps/web/src/stock/StockDetailDrawer.tsx`
- Modify: `apps/web/src/pages/Paper.tsx`
- Modify: `apps/web/src/pages/Watchlist.tsx`

- [ ] **Step 1: Drawer**

使用 HeroUI `Drawer`（若 v3 无则用固定 `aside` + 遮罩）：

- 打开时渲染 `StockDetailView compact` + `onExpand` → `navigate(/stock/${symbol}, { state: { position } })` 并关闭抽屉。  
- `onClose` 清空本地 symbol state。

- [ ] **Step 2: Paper**

- `useState<{symbol, position} | null>`  
- 持仓行 `symbol` 单元格加 `button`/`cursor-pointer`，点击设置 drawer 状态（传入 qty/cost/pnl/weightPct）。  
- 页面底部或 portal 挂载 `StockDetailDrawer`。

- [ ] **Step 3: Watchlist**

- 行点击打开抽屉，**不传** position。

- [ ] **Step 4: Manual checklist（实现者本地点验）**

- 持仓开抽屉见仓位条 → 展开 URL 正确且仓位条可收起  
- 自选开抽屉无仓位条  

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): stock detail drawer from monitor and watchlist"
```

---

### Task 8: 壳层顶部搜索

**Files:**
- Modify: `apps/web/src/layout/AppShell.tsx`
- Test: `apps/web/src/layout/nav.test.ts`（若仅改 shell，可新增 `AppShell` 无关；改为 `stock/symbolPath.test.ts`）

- [ ] **Step 1: 纯函数 + 测试**

```typescript
/** 将用户输入规范为路由 symbol；非法返回 null */
export function parseSearchSymbol(raw: string): string | null {
  const s = raw.trim().toUpperCase();
  if (!s) return null;
  if (/^\d{6}$/.test(s)) {
    const head = s[0];
    const suffix = head === "5" || head === "6" || head === "9" ? "SH" : "SZ";
    return `${s}.${suffix}`;
  }
  if (/^\d{6}\.(SH|SZ)$/.test(s)) return s;
  return null;
}
```

`apps/web/src/stock/parseSearchSymbol.test.ts`：覆盖 `600519` → `600519.SH`、`000001.SZ` 原样、空串 null。

Run: `cd apps/web && npm test`

- [ ] **Step 2: AppShell UI**

顶栏加 `Input` + 提交：`navigate(/stock/${parseSearchSymbol(q)})`；解析失败时不跳转（可 `setLog` 若 shell 无 log，则忽略或 title 旁短暂提示）。

搜索直达全页，不经抽屉。

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(web): shell search navigates to stock detail"
```

---

### Task 9: 联调验收与文档状态

**Files:**
- Modify: `docs/superpowers/specs/2026-07-16-stock-detail-design.md`（状态改为「实现中/已完成」）

- [ ] **Step 1: Backend suite**

```powershell
$env:DATABASE_URL="sqlite:///:memory:"
$env:MARKET_SCHEDULER_ENABLED="0"
pytest tests/test_stock_detail_aggregate.py tests/test_stock_detail_api.py -v
```

Expected: PASS

- [ ] **Step 2: Frontend**

```powershell
cd E:\study\AiMakeMoney\apps\web
npm test
npm run build
```

Expected: PASS

- [ ] **Step 3: Manual（对照 spec 测试要点）**

| 项 | 结果 |
|----|------|
| 持仓 → 抽屉 → 展开 | |
| 自选 → 抽屉无仓位 | |
| 搜索 → 全页 | |
| 分时/日/周/月 | |
| 缺资金票空态 | |
| 非法代码 meta 404 提示 | |

- [ ] **Step 4: 更新 spec 状态为已完成（若验收通过）并 commit**

```bash
git commit -m "docs(spec): mark stock detail design completed"
```

---

## Self-Review（对照 spec）

| Spec 要求 | 任务 |
|-----------|------|
| 入口持仓/自选/搜索 | Task 7–8 |
| 模块行情/图/基本/板块/资金/技术 | Task 2–6 |
| 库优先 + live | Task 4；technicals 以库日线为主（Task 3） |
| 抽屉 + 展开全页 | Task 6–7 |
| 分时+日/周/月 | Task 3 + 5–6 |
| 仓位摘要可收起 | Task 6–7 |
| capital/technicals `available: false` | Task 3–4 |
| 非法 symbol 404 | Task 2 |
| 无 WebSocket / 无分钟多周期 | 明确不做 |

**占位符：** 无 TBD。Task 3 seed 写法注明以现有 upsert 测试为准。  
**类型一致性：** `PositionContext`、`available`、`source`、`latest.main_net` / `latest.ma5` 前后统一。
