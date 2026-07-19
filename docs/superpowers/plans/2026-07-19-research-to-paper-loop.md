# Research-to-Paper 闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对照 AISeeValue，把本项目从「研究台」补成「策略可自动跑、成本/KPI/闸门口径一致」的纸交易闭环，再逐步接审批与真 QMT。

**Architecture:** 复用现有 `on_bar` → `Signal` → `OrderIntent` → `PaperBroker`/`RiskGate` 合约；新增 Paper Runner 调度；成本模型从 `desk_backtest.commission` 抽到共用模块；Walk-Forward 写 KPI；生命周期闸门卡买入；最后开审批/真单与增强项。

**Tech Stack:** FastAPI、SQLAlchemy、desk_strategy / desk_broker / desk_backtest、APScheduler（可选）、pytest、React（监控页触发/状态）

**对照结论（勿颠倒优先级）：** 本项目行情管道/测试/UI 已更强；缺口在自动执行与口径一致。

---

## 落地顺序（总览）

| Phase | 名称 | 交付物 | 依赖 |
| ----- | ---- | ------ | ---- |
| 1 | Paper Runner | `run_once`：策略信号→纸单；API + 测试 + 监控页入口 | 无 |
| 2 | 成本与权益对齐 | 纸交易佣金/印花税/滑点；持仓 mark-to-market 权益 | Phase 1 |
| 3 | Walk-Forward + KPI | IS/OOS 自动算并写入 `StrategyKPI` | 回测引擎 |
| 4 | 晋升闸门 | 非 probation/production 禁买或 qty=0 | Phase 1+3 |
| 5 | 审批 + 真 QMT | dry-run / 审批 / 自动；真单接线（默认关） | Phase 1+4 |
| 6 | 增强 | 归因、执行质量、晨会一键进自选 | Phase 2+ |

---

## 文件结构（跨 Phase）

| 路径 | 职责 |
| ---- | ---- |
| `packages/broker/desk_broker/paper_runner.py` | Phase1：一次扫描、信号转订单 |
| `packages/broker/desk_broker/trading_cost.py` | Phase2：共用成交成本（从 commission 抽取） |
| `packages/broker/desk_broker/promotion_gate.py` | Phase4：阶段是否允许买入 |
| `packages/backtest/desk_backtest/walk_forward.py` | Phase3：IS/OOS 切分回测 |
| `packages/broker/desk_broker/order_executor.py` | Phase5：幂等/审批/路由 |
| `apps/api/app/routes/broker.py` | Runner / 审批 API |
| `apps/web/src/pages/Paper.tsx` | 触发 run-once、展示最近信号 |
| `tests/test_paper_runner.py` 等 | 各 Phase 测试 |

---

## Phase 1: Paper Runner

### Task 1.1: 失败测试 — `run_once` 买信号下纸单

**Files:**
- Create: `tests/test_paper_runner.py`
- Create: `packages/broker/desk_broker/paper_runner.py`
- Modify: `packages/broker/desk_broker/__init__.py`（导出）

- [x] **Step 1: 写失败测试**

```python
"""Paper Runner：策略 on_bar → PaperBroker 成交。"""
import os
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_broker.paper_runner import PaperStrategyRunner
from desk_broker import PaperBroker
from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
from desk_market import MarketService
import desk_db.models  # noqa: F401


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    yield Session(get_engine())
    reset_engine()
    get_settings.cache_clear()


def _seed_uptrend(db: Session, symbol: str = "600519.SH"):
    svc = MarketService(db)
    today = date.today()
    price = 100.0
    rows = []
    for i in range(80, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        price *= 1.01
        rows.append({
            "date": d, "open": price * 0.99, "high": price * 1.01,
            "low": price * 0.98, "close": price, "volume": 1e6,
            "amount": price * 1e6,
            "open_hfq": price * 0.99, "high_hfq": price * 1.01,
            "low_hfq": price * 0.98, "close_hfq": price, "volume_hfq": 1e6,
        })
    svc.upsert_daily_bars(symbol, pd.DataFrame(rows))
    db.commit()


def test_run_once_ma_cross_places_or_skips(db: Session):
    """有 K 线时 run_once 应返回结构化结果，且不抛错。"""
    _seed_uptrend(db)
    runner = PaperStrategyRunner(db)
    result = runner.run_once(strategy_id="ma_cross", symbol="600519.SH")
    assert result["strategy_id"] == "ma_cross"
    assert result["symbol"] == "600519.SH"
    assert "signals" in result
    assert "orders" in result
    # 金叉时可能下买单；无论是否成交，status 应为 ok
    assert result["status"] == "ok"
```

- [x] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_paper_runner.py::test_run_once_ma_cross_places_or_skips -v
```

Expected: `ImportError` 或 `ModuleNotFoundError: paper_runner`

- [x] **Step 3: 实现 `PaperStrategyRunner`**

`packages/broker/desk_broker/paper_runner.py`：

```python
"""纸交易策略 Runner：复用回测同款 on_bar 上下文，信号转 Paper 订单。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from desk_common.contracts import OrderIntent, Side
from desk_indicators import compute
from desk_strategy import StrategyRegistry
from desk_strategy.bar_context import build_bar_row

from desk_broker import PaperBroker


class PaperStrategyRunner:
    """
    对单标的跑一次策略评估并下纸单。

    口径对齐回测：用日线 history + build_bar_row；买仅空仓、卖仅平仓。
    """

    def __init__(self, db: Session, *, account_name: str = "default"):
        self.db = db
        self.broker = PaperBroker(db, account_name=account_name)
        self.registry = StrategyRegistry(db)

    def run_once(self, *, strategy_id: str, symbol: str) -> dict[str, Any]:
        """
        评估最新一根可用 K 线并尝试下单。

        @param strategy_id: 策略 ID
        @param symbol: 标的
        @returns: status / signals / orders / message
        """
        reg = self.registry.load(strategy_id)
        if not reg or not reg.on_bar:
            return {
                "status": "error",
                "strategy_id": strategy_id,
                "symbol": symbol,
                "signals": [],
                "orders": [],
                "message": f"strategy not runnable: {strategy_id}",
            }

        from desk_market import MarketService

        df = MarketService(self.db).load_daily_bars(symbol)
        if df is None or getattr(df, "empty", True) or len(df) < 30:
            return {
                "status": "error",
                "strategy_id": strategy_id,
                "symbol": symbol,
                "signals": [],
                "orders": [],
                "message": "insufficient bars",
            }

        df = compute(df.copy())
        history = df
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
        signals = reg.on_bar({"row": row, "history": history}) or []
        sig_dump = [s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in signals]

        summary = self.broker.summary()
        held = {p["symbol"]: p["qty"] for p in summary.get("positions") or []}
        last_price = float(df.iloc[-1]["close"])
        orders: list[dict[str, Any]] = []

        for sig in signals:
            side = sig.side if hasattr(sig, "side") else Side(sig["side"])
            if side == Side.BUY and held.get(symbol, 0) > 0:
                continue
            if side == Side.SELL and held.get(symbol, 0) <= 0:
                continue
            qty = float(sig.qty) if getattr(sig, "qty", None) else None
            if qty is None or qty <= 0:
                if side == Side.BUY:
                    cash = float(summary["cash"])
                    qty = int((cash * 0.95) / last_price / 100) * 100
                else:
                    qty = float(held.get(symbol, 0))
            if qty < 100 and side == Side.BUY:
                continue
            if qty <= 0:
                continue
            intent = OrderIntent(
                symbol=symbol,
                side=side,
                qty=qty,
                price=last_price,
                client_order_id=f"paper|{strategy_id}|{symbol}|{uuid4().hex[:12]}",
                strategy_id=strategy_id,
                mode="paper",
            )
            result = self.broker.place_order(intent)
            orders.append(result.model_dump())
            summary = self.broker.summary()
            held = {p["symbol"]: p["qty"] for p in summary.get("positions") or []}
            break  # 与回测一致：一 bar 一单

        self.db.flush()
        return {
            "status": "ok",
            "strategy_id": strategy_id,
            "symbol": symbol,
            "signals": sig_dump,
            "orders": orders,
            "last_price": last_price,
            "message": "",
        }
```

注意：实现时核对 `MarketService` 是否已有 `load_daily_bars`；若无则用现有读 bar API（如 `get_daily` / SQL 查 `BarDaily`），以仓库实际方法名为准。

- [x] **Step 4: 导出并跑通测试**

```bash
pytest tests/test_paper_runner.py -v
```

Expected: PASS

- [x] **Step 5: Commit**（与 Task 1.2 一并提交）

### Task 1.2: API + 监控页入口

**Files:**
- Modify: `apps/api/app/routes/broker.py`
- Modify: `apps/web/src/pages/Paper.tsx`

- [x] **Step 1: API**

```python
class PaperRunIn(BaseModel):
    strategy_id: str
    symbol: str

@router.post("/paper/run-once")
def paper_run_once(body: PaperRunIn, db: Session = Depends(get_db)):
    """对单标的跑一次纸交易策略评估并下单。"""
    from desk_broker.paper_runner import PaperStrategyRunner
    return PaperStrategyRunner(db).run_once(
        strategy_id=body.strategy_id, symbol=body.symbol
    )
```

- [x] **Step 2: Paper 页增加「跑一次」按钮**（策略下拉 + 标的输入，调用上述 API，结果写 setLog）

- [x] **Step 3: 测试 + Commit**

### Task 1.3: 批量 — 自选 × 默认策略（可选同 Phase）

- [x] `run_watchlist(strategy_id)`：遍历 `WatchlistItem`，逐个 `run_once`，汇总结果  
- [x] API `POST /api/broker/paper/run-watchlist`  
- [x] Commit

---

## Phase 2: 纸交易成本与权益对齐 — ✅ 已完成

- 共用 `desk_common/trading_cost.py`；纸交易扣佣金/印花税/滑点；权益 mark-to-market  
- Commit: `56520c6`

## Phase 3: Walk-Forward + KPI — ✅ 已完成

- `desk_backtest/walk_forward.py`；孵化评估自动补算；API `.../lifecycle/walk-forward`  
- Commit: `1b52353`

## Phase 4: 生命周期晋升闸门 — ✅ 已完成

- `promotion_gate.py`；Runner 仅 probation/production 可买  
- Commit: `493fb36`

## Phase 5: 审批模式 + 真 QMT — ✅ 已完成（真单仍 Mock 落库）

- 默认 live → `awaiting_approval`；`AUTO_EXECUTE_LIVE` + `I_UNDERSTAND_AUTO_LIVE` 才自动成交  
- Approvals API；xtquant 探测后仍 Mock，message 提示待接真柜台  
- Commit: `5ad7af2`

## Phase 6: 增强项 — ✅ 已完成（轻量）

- 执行质量 `/api/review/analytics/execution-quality`  
- 轻量归因 `/api/review/analytics/attribution`  
- 晨会进自选 `POST /api/morning/bind`

---

## 验收标准

1. ✅ 监控页「跑一次」/「跑自选」  
2. ✅ 纸账户费用与市值权益  
3. ✅ WF ratio 写入 KPI  
4. ✅ 非试用/主力 Runner 不开仓  
5. ✅ 自动实盘双开关默认关  
6. ✅ 晨会 bind + 执行质量/轻量归因 API

---

## 执行说明

本会话已按 Phase 1→6 Inline 完成并分 commit。后续可选：定时调度 Runner、xtquant 真单、完整 Brinson。
