# TA-Lib 因子目录与主/副图展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 因子页提供可勾选的 TA-Lib 因子目录，并按主图 overlay + 下方 panel 副图展示序列。

**Architecture:** `FactorRegistry` 描述元数据；扩展 `desk_indicators.compute`；`FactorService` 提供 `list_factors` / `compute_series`；API `GET /api/factors` 与 `GET /api/factors/series`；前端左栏目录（已选常显、未选分类折叠）+ 右栏 lightweight-charts。

**Tech Stack:** Python 3、pandas、TA-Lib（可选降级）、FastAPI、SQLAlchemy `bars_daily`、React 19、lightweight-charts、Vitest、pytest。

**Spec:** `docs/superpowers/specs/2026-07-21-talib-factors-charts-design.md`

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| Create: `packages/factor/desk_factor/registry.py` | `FactorMeta` TypedDict/dataclass + `FACTOR_REGISTRY` 常量 |
| Modify: `packages/factor/desk_factor/__init__.py` | `list_factors` 读注册表；新增 `compute_series` |
| Modify: `packages/indicators/desk_indicators/__init__.py` | 补 STOCH/CCI/ADX/OBV/MOM 等；未知 spec 抛错 |
| Create: `tests/test_factor_registry.py` | 默认启用名单与字段断言 |
| Create: `tests/test_indicators_extra.py` | 新指标 + 未知名错误 |
| Create: `tests/test_factor_series.py` | `compute_series` 与 API 契约 |
| Modify: `apps/api/app/routes/factor_ml.py` | `{factors}` 响应；新增 `/factors/series` |
| Create: `apps/web/src/factors/types.ts` | 前后端对齐的 TS 类型 |
| Create: `apps/web/src/factors/FactorCatalog.tsx` | 左栏：已选 + 折叠分类 |
| Create: `apps/web/src/factors/FactorCharts.tsx` | 主图 + 多副图、时间轴联动 |
| Create: `apps/web/src/factors/groupFactors.ts` | 已选/分类分组纯函数 |
| Create: `apps/web/src/factors/groupFactors.test.ts` | 分组单测 |
| Modify: `apps/web/src/pages/Factors.tsx` | 左右布局接线；ML 区块保留在图表下方 |

---

### Task 1: FactorRegistry

**Files:**
- Create: `packages/factor/desk_factor/registry.py`
- Create: `tests/test_factor_registry.py`

- [ ] **Step 1: 写失败单测**

```python
"""FactorRegistry 一期默认名单与字段。"""

from __future__ import annotations

from desk_factor.registry import FACTOR_REGISTRY, default_enabled_names


def test_default_enabled_names():
    assert set(default_enabled_names()) == {
        "SMA_5",
        "SMA_20",
        "SMA_60",
        "EMA_12",
        "EMA_26",
        "BOLL",
        "RSI_14",
        "MACD",
        "ATR_14",
        "STOCH",
        "CCI_14",
        "ADX_14",
        "OBV",
        "MOM_10",
    }


def test_registry_has_required_fields_and_plots():
    by_name = {f["name"]: f for f in FACTOR_REGISTRY}
    assert by_name["SMA_20"]["plot"] == "overlay"
    assert by_name["RSI_14"]["plot"] == "panel"
    assert by_name["STOCH"]["label"]  # 展示可用「KD」
    for f in FACTOR_REGISTRY:
        assert f["enabled"] is True
        assert f["category"]
        assert isinstance(f["params"], dict)
        assert isinstance(f["outputs"], list) and f["outputs"]
        assert f["plot"] in ("overlay", "panel")


def test_extra_registered_but_disabled_by_default():
    """至少有一个非默认开的因子，供折叠分类展示。"""
    extras = [f for f in FACTOR_REGISTRY if not f["default_enabled"]]
    assert any(f["name"] == "SMA_10" for f in extras)
    assert any(f["name"] == "WILLR_14" for f in extras)
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_factor_registry.py -v`

Expected: FAIL（`desk_factor.registry` 不存在）

- [ ] **Step 3: 实现 registry**

```python
"""TA-Lib / 技术因子注册表。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class FactorMeta(TypedDict):
    name: str
    label: str
    category: str
    params: dict[str, Any]
    outputs: list[str]
    plot: Literal["overlay", "panel"]
    default_enabled: bool
    enabled: bool


def _f(
    name: str,
    *,
    label: str | None = None,
    category: str,
    params: dict[str, Any] | None = None,
    outputs: list[str] | None = None,
    plot: Literal["overlay", "panel"],
    default_enabled: bool = False,
) -> FactorMeta:
    return {
        "name": name,
        "label": label or name,
        "category": category,
        "params": params or {},
        "outputs": outputs or [name.lower()],
        "plot": plot,
        "default_enabled": default_enabled,
        "enabled": True,
    }


FACTOR_REGISTRY: list[FactorMeta] = [
    _f("SMA_5", category="trend", params={"period": 5}, outputs=["sma_5"], plot="overlay", default_enabled=True),
    _f("SMA_10", category="trend", params={"period": 10}, outputs=["sma_10"], plot="overlay"),
    _f("SMA_20", category="trend", params={"period": 20}, outputs=["sma_20"], plot="overlay", default_enabled=True),
    _f("SMA_60", category="trend", params={"period": 60}, outputs=["sma_60"], plot="overlay", default_enabled=True),
    _f("EMA_12", category="trend", params={"period": 12}, outputs=["ema_12"], plot="overlay", default_enabled=True),
    _f("EMA_26", category="trend", params={"period": 26}, outputs=["ema_26"], plot="overlay", default_enabled=True),
    _f(
        "BOLL",
        category="volatility",
        params={"period": 20, "nbdev": 2},
        outputs=["boll_mid", "boll_upper", "boll_lower"],
        plot="overlay",
        default_enabled=True,
    ),
    _f("ADX_14", category="trend", params={"period": 14}, outputs=["adx_14"], plot="panel", default_enabled=True),
    _f("RSI_14", category="momentum", params={"period": 14}, outputs=["rsi_14"], plot="panel", default_enabled=True),
    _f(
        "MACD",
        category="momentum",
        params={"fast": 12, "slow": 26, "signal": 9},
        outputs=["macd", "macd_signal", "macd_hist"],
        plot="panel",
        default_enabled=True,
    ),
    _f(
        "STOCH",
        label="KD",
        category="momentum",
        params={"fastk": 5, "slowk": 3, "slowd": 3},
        outputs=["stoch_k", "stoch_d"],
        plot="panel",
        default_enabled=True,
    ),
    _f("CCI_14", category="momentum", params={"period": 14}, outputs=["cci_14"], plot="panel", default_enabled=True),
    _f("MOM_10", category="momentum", params={"period": 10}, outputs=["mom_10"], plot="panel", default_enabled=True),
    _f("WILLR_14", category="momentum", params={"period": 14}, outputs=["willr_14"], plot="panel"),
    _f("ATR_14", category="volatility", params={"period": 14}, outputs=["atr_14"], plot="panel", default_enabled=True),
    _f("OBV", category="volume", outputs=["obv"], plot="panel", default_enabled=True),
]


def default_enabled_names() -> list[str]:
    """一期默认勾选的因子 name 列表。"""
    return [f["name"] for f in FACTOR_REGISTRY if f["default_enabled"] and f["enabled"]]


def get_factor(name: str) -> FactorMeta | None:
    """按 name 查找（大小写不敏感）。"""
    key = name.upper()
    for f in FACTOR_REGISTRY:
        if f["name"].upper() == key:
            return f
    return None


def list_enabled_registry() -> list[FactorMeta]:
    """目录可见项。"""
    return [f for f in FACTOR_REGISTRY if f["enabled"]]
```

- [ ] **Step 4: 跑测确认通过**

Run: `pytest tests/test_factor_registry.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/factor/desk_factor/registry.py tests/test_factor_registry.py
git commit -m "feat(factor): 增加 TA-Lib 因子注册表与默认启用名单"
```

---

### Task 2: 扩展 desk_indicators

**Files:**
- Modify: `packages/indicators/desk_indicators/__init__.py`
- Create: `tests/test_indicators_extra.py`

- [ ] **Step 1: 写失败单测**

```python
"""扩展指标：STOCH/CCI/ADX/OBV/MOM 与未知名。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from desk_indicators import HAS_TALIB, compute


def _ohlcv(n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + 1
    low = close - 1
    open_ = close
    volume = rng.integers(1000, 5000, n).astype(float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def test_compute_extra_indicators_columns():
    df = compute(_ohlcv(), ["STOCH", "CCI_14", "ADX_14", "OBV", "MOM_10", "SMA_60", "EMA_26", "WILLR_14"])
    for col in ("stoch_k", "stoch_d", "cci_14", "adx_14", "obv", "mom_10", "sma_60", "ema_26", "willr_14"):
        assert col in df.columns
        assert df[col].notna().sum() > 0


def test_unknown_spec_raises():
    with pytest.raises(ValueError, match="unknown"):
        compute(_ohlcv(30), ["NOT_A_REAL_FACTOR"])


def test_engine_flag_matches_has_talib():
    from desk_indicators import last_engine

    compute(_ohlcv(40), ["SMA_5"])
    assert last_engine() in ("talib", "python")
    assert (last_engine() == "talib") == HAS_TALIB
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_indicators_extra.py -v`

Expected: FAIL（缺列或未知名未抛错）

- [ ] **Step 3: 实现扩展**

在 `desk_indicators/__init__.py`：

1. 增加模块级 `_LAST_ENGINE: str = "python"` 与 `def last_engine() -> str: return _LAST_ENGINE`。
2. `compute` 开头设 `_LAST_ENGINE = "talib" if HAS_TALIB else "python"`（各 `_xxx` 已按 HAS_TALIB 分支；若某函数无 talib 实现则在该分支内把 `_LAST_ENGINE = "python"`）。
3. 在 `for spec in specs` 循环末尾对未知 key：`raise ValueError(f"unknown indicator: {spec}")`。
4. 新增分支与 helper（TA-Lib 优先，否则 pandas 近似）：

```python
elif key == "STOCH":
    k, d = _stoch(high, low, close)
    df["stoch_k"], df["stoch_d"] = k, d
elif key.startswith("CCI_"):
    n = int(key.split("_")[1])
    df[f"cci_{n}"] = _cci(high, low, close, n)
elif key.startswith("ADX_"):
    n = int(key.split("_")[1])
    df[f"adx_{n}"] = _adx(high, low, close, n)
elif key == "OBV":
    df["obv"] = _obv(close, df["volume"].astype(float).values)
elif key.startswith("MOM_"):
    n = int(key.split("_")[1])
    df[f"mom_{n}"] = _mom(close, n)
elif key.startswith("WILLR_"):
    n = int(key.split("_")[1])
    df[f"willr_{n}"] = _willr(high, low, close, n)
else:
    raise ValueError(f"unknown indicator: {spec}")
```

`_stoch`：`talib.STOCH` 或 `%K/%D` 滚动实现；`_cci`：`talib.CCI` 或典型价滚动；`_adx`：`talib.ADX` 或简化 DX 滚动；`_obv`：`talib.OBV` 或符号累加；`_mom`：`talib.MOM` 或 `close - close.shift(n)`；`_willr`：`talib.WILLR` 或威廉指标公式。

注意：现有 `MACD` 列名已是 `macd` / `macd_signal` / `macd_hist`，与 registry `outputs` 对齐。

- [ ] **Step 4: 跑测确认通过**

Run: `pytest tests/test_indicators_extra.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/indicators/desk_indicators/__init__.py tests/test_indicators_extra.py
git commit -m "feat(indicators): 扩展 STOCH/CCI/ADX/OBV/MOM 并拒绝未知指标"
```

---

### Task 3: FactorService.compute_series

**Files:**
- Modify: `packages/factor/desk_factor/__init__.py`
- Create: `tests/test_factor_series.py`（先写服务层部分）

- [ ] **Step 1: 写失败单测（服务层）**

```python
"""FactorService.compute_series 契约。"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from desk_factor import FactorService


def _bars(n: int = 60) -> pd.DataFrame:
    start = date(2024, 1, 2)
    rows = []
    px = 100.0
    for i in range(n):
        px += 0.5
        d = start + timedelta(days=i)
        rows.append(
            {
                "date": d,
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px,
                "volume": 1000.0,
            }
        )
    return pd.DataFrame(rows)


def test_list_factors_wrapped_shape():
    rows = FactorService().list_factors()
    assert isinstance(rows, list)
    assert rows[0]["name"] == "SMA_5"
    assert "plot" in rows[0]
    assert "default_enabled" in rows[0]


def test_compute_series_returns_bars_and_outputs():
    out = FactorService().compute_series_from_df(_bars(), ["SMA_20", "RSI_14", "MACD"])
    assert out["engine"] in ("talib", "python")
    assert len(out["bars"]) == 60
    assert "sma_20" in out["series"]["SMA_20"]["outputs"]
    assert "rsi_14" in out["series"]["RSI_14"]["outputs"]
    assert set(out["series"]["MACD"]["outputs"]) >= {"macd", "macd_signal", "macd_hist"}
    # 有效值点
    vals = out["series"]["SMA_20"]["outputs"]["sma_20"]
    assert any(p["v"] is not None for p in vals)


def test_compute_series_unknown_name():
    with pytest.raises(ValueError, match="unknown"):
        FactorService().compute_series_from_df(_bars(30), ["NOPE"])
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_factor_series.py::test_list_factors_wrapped_shape tests/test_factor_series.py::test_compute_series_returns_bars_and_outputs tests/test_factor_series.py::test_compute_series_unknown_name -v`

Expected: FAIL

- [ ] **Step 3: 实现 FactorService**

替换/扩展 `packages/factor/desk_factor/__init__.py`：

```python
"""选股因子与 TA-Lib 序列。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from desk_indicators import compute, last_engine
from desk_factor.registry import get_factor, list_enabled_registry
from desk_market import MarketService


class FactorService:
    """因子目录与基于日线的序列计算。"""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def list_factors(self) -> list[dict[str, Any]]:
        """返回注册表可见因子（含 plot / default_enabled）。"""
        return [dict(f) for f in list_enabled_registry()]

    def compute_series_from_df(self, ohlcv: pd.DataFrame, names: list[str]) -> dict[str, Any]:
        """
        在内存 OHLCV 上计算因子序列。

        @raises ValueError: 未知因子名
        """
        resolved = []
        for raw in names:
            meta = get_factor(raw)
            if meta is None:
                raise ValueError(f"unknown factor: {raw}")
            resolved.append(meta)

        specs = [m["name"] for m in resolved]
        df = compute(ohlcv, specs)
        bars = [
            {
                "date": str(r["date"])[:10] if not isinstance(r["date"], str) else r["date"][:10],
                "o": float(r["open"]),
                "h": float(r["high"]),
                "l": float(r["low"]),
                "c": float(r["close"]),
                "v": float(r["volume"]),
            }
            for _, r in df.iterrows()
        ]
        series: dict[str, Any] = {}
        for meta in resolved:
            outputs: dict[str, list[dict[str, Any]]] = {}
            for col in meta["outputs"]:
                points = []
                for _, r in df.iterrows():
                    d = str(r["date"])[:10]
                    val = r[col]
                    points.append({"date": d, "v": None if pd.isna(val) else float(val)})
                outputs[col] = points
            series[meta["name"]] = {"outputs": outputs}
        return {"engine": last_engine(), "bars": bars, "series": series}

    def compute_series(
        self,
        symbol: str,
        names: list[str],
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """
        从 bars_daily 加载并计算。

        @raises ValueError: 无日线或未知因子
        """
        if self.db is None:
            raise ValueError("db required")
        end = end or date.today()
        start = start or date(end.year - 1, end.month, end.day)
        df = MarketService(self.db).load_daily_df(symbol, start, end)
        if df.empty:
            raise ValueError("无本地日线")
        out = self.compute_series_from_df(df, names)
        out["symbol"] = symbol
        return out
```

保留原有 `compute(ohlcv)` 特征矩阵方法（若其它代码依赖），内部继续 `from desk_indicators import compute as compute_indicators` 并附加 `amount_z20`（AMOUNT_Z20 不在一期注册表即可）。

- [ ] **Step 4: 跑测确认通过**

Run: `pytest tests/test_factor_series.py::test_list_factors_wrapped_shape tests/test_factor_series.py::test_compute_series_returns_bars_and_outputs tests/test_factor_series.py::test_compute_series_unknown_name -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/factor/desk_factor/__init__.py tests/test_factor_series.py
git commit -m "feat(factor): FactorService 按注册表计算因子序列"
```

---

### Task 4: API `/api/factors` 与 `/api/factors/series`

**Files:**
- Modify: `apps/api/app/routes/factor_ml.py`
- Modify: `tests/test_factor_series.py`（追加 API 用例）

- [ ] **Step 1: 写失败 API 单测**

在 `tests/test_factor_series.py` 追加（复用 `test_stock_detail_api` 的 client / seed 模式）：

```python
import os
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_market import MarketService


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
def client(_db, monkeypatch):
    import app as app_pkg

    monkeypatch.setattr(app_pkg, "try_ensure_schema", lambda: True)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _seed_symbol(symbol: str = "600519.SH", n: int = 40) -> None:
    from desk_db import get_session_factory

    rows = []
    d0 = date(2024, 6, 1)
    for i in range(n):
        c = 100 + i * 0.2
        rows.append(
            {
                "date": d0 + timedelta(days=i),
                "open": c,
                "high": c + 1,
                "low": c - 1,
                "close": c,
                "volume": 1000,
                "amount": 10000,
                "open_hfq": c,
                "high_hfq": c + 1,
                "low_hfq": c - 1,
                "close_hfq": c,
                "volume_hfq": 1000,
            }
        )
    sf = get_session_factory()
    db = sf()
    try:
        MarketService(db).upsert_daily_bars(symbol, rows)
        db.commit()
    finally:
        db.close()


def test_api_factors_catalog(client):
    r = client.get("/api/factors")
    assert r.status_code == 200
    body = r.json()
    assert "factors" in body
    assert any(f["name"] == "MACD" for f in body["factors"])


def test_api_factors_series_ok(client):
    _seed_symbol()
    r = client.get(
        "/api/factors/series",
        params={"symbol": "600519.SH", "names": "SMA_20,RSI_14", "start": "2024-06-01", "end": "2024-08-01"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "600519.SH"
    assert body["bars"]
    assert "SMA_20" in body["series"]


def test_api_factors_series_no_bars(client):
    r = client.get("/api/factors/series", params={"symbol": "000001.SZ", "names": "SMA_5"})
    assert r.status_code == 400
    assert "无本地日线" in r.text


def test_api_factors_series_unknown(client):
    _seed_symbol("600000.SH")
    r = client.get("/api/factors/series", params={"symbol": "600000.SH", "names": "NOPE"})
    assert r.status_code == 400
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_factor_series.py::test_api_factors_catalog tests/test_factor_series.py::test_api_factors_series_ok -v`

Expected: FAIL（响应仍是 list 或无 series 路由）

- [ ] **Step 3: 改路由**

```python
@router.get("/factors")
def factors():
    return {"factors": FactorService().list_factors()}


@router.get("/factors/series")
def factor_series(
    symbol: str,
    names: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    if not name_list:
        raise HTTPException(400, "names required")
    try:
        return FactorService(db).compute_series(symbol, name_list, start=start, end=end)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
```

- [ ] **Step 4: 跑全文件测试**

Run: `pytest tests/test_factor_series.py tests/test_factor_registry.py tests/test_indicators_extra.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routes/factor_ml.py tests/test_factor_series.py
git commit -m "feat(api): 因子目录包装响应与 /factors/series"
```

---

### Task 5: 前端分组纯函数

**Files:**
- Create: `apps/web/src/factors/types.ts`
- Create: `apps/web/src/factors/groupFactors.ts`
- Create: `apps/web/src/factors/groupFactors.test.ts`

- [ ] **Step 1: 写失败单测**

```typescript
import { describe, expect, it } from "vitest";
import { groupFactorCatalog } from "./groupFactors";
import type { FactorMeta } from "./types";

const sample: FactorMeta[] = [
  { name: "SMA_20", label: "SMA 20", category: "trend", params: {}, outputs: ["sma_20"], plot: "overlay", default_enabled: true, enabled: true },
  { name: "SMA_10", label: "SMA 10", category: "trend", params: {}, outputs: ["sma_10"], plot: "overlay", default_enabled: false, enabled: true },
  { name: "RSI_14", label: "RSI 14", category: "momentum", params: {}, outputs: ["rsi_14"], plot: "panel", default_enabled: true, enabled: true },
  { name: "WILLR_14", label: "WILLR", category: "momentum", params: {}, outputs: ["willr_14"], plot: "panel", default_enabled: false, enabled: true },
];

describe("groupFactorCatalog", () => {
  it("splits selected vs collapsed categories for unselected", () => {
    const selected = new Set(["SMA_20", "RSI_14"]);
    const g = groupFactorCatalog(sample, selected);
    expect(g.selected.map((f) => f.name)).toEqual(["SMA_20", "RSI_14"]);
    expect(g.collapsedCategories.map((c) => c.category)).toEqual(["trend", "momentum"]);
    expect(g.collapsedCategories.find((c) => c.category === "trend")!.items.map((i) => i.name)).toEqual(["SMA_10"]);
  });
});
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd apps/web && npm test -- src/factors/groupFactors.test.ts`

Expected: FAIL

- [ ] **Step 3: 实现 types + groupFactors**

```typescript
// types.ts
export type FactorPlot = "overlay" | "panel";

export type FactorMeta = {
  name: string;
  label: string;
  category: string;
  params: Record<string, unknown>;
  outputs: string[];
  plot: FactorPlot;
  default_enabled: boolean;
  enabled: boolean;
};

export type FactorPoint = { date: string; v: number | null };

export type FactorSeriesResponse = {
  symbol: string;
  engine: "talib" | "python";
  bars: { date: string; o: number; h: number; l: number; c: number; v: number }[];
  series: Record<string, { outputs: Record<string, FactorPoint[]> }>;
};
```

```typescript
// groupFactors.ts
import type { FactorMeta } from "./types";

export type CollapsedCategory = { category: string; items: FactorMeta[] };

/**
 * 左栏：已选常显；未选按分类折叠。
 * @param factors 目录
 * @param selected 勾选 name 集合
 */
export function groupFactorCatalog(
  factors: FactorMeta[],
  selected: Set<string>
): { selected: FactorMeta[]; collapsedCategories: CollapsedCategory[] } {
  const selectedRows = factors.filter((f) => selected.has(f.name));
  const unselected = factors.filter((f) => !selected.has(f.name));
  const map = new Map<string, FactorMeta[]>();
  for (const f of unselected) {
    const list = map.get(f.category) ?? [];
    list.push(f);
    map.set(f.category, list);
  }
  const collapsedCategories = [...map.entries()].map(([category, items]) => ({ category, items }));
  return { selected: selectedRows, collapsedCategories };
}
```

- [ ] **Step 4: 跑测通过**

Run: `cd apps/web && npm test -- src/factors/groupFactors.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/factors/types.ts apps/web/src/factors/groupFactors.ts apps/web/src/factors/groupFactors.test.ts
git commit -m "feat(web): 因子目录已选/折叠分类分组"
```

---

### Task 6: FactorCatalog + FactorCharts + Factors 页接线

**Files:**
- Create: `apps/web/src/factors/FactorCatalog.tsx`
- Create: `apps/web/src/factors/FactorCharts.tsx`
- Modify: `apps/web/src/pages/Factors.tsx`

- [ ] **Step 1: 实现 FactorCatalog**

左栏结构：

- 搜索框过滤 `label`/`name`
- 「已选」小节：checkbox 列表（取消勾选即移出）
- 下方各类：`<details>` 默认折叠，内为未选项 checkbox
- props：`factors`、`selected: Set<string>`、`onToggle(name)`、`query`/`onQuery`

副图上限：父组件在 toggle 时若 panel 勾选将超过 6，则 `setLog` 提示并拒绝勾选。

- [ ] **Step 2: 实现 FactorCharts**

参考 `apps/web/src/stock/StockChart.tsx` 的 `createChart` / `CandlestickSeries` / `LineSeries` / `HistogramSeries`：

- 接收 `data: FactorSeriesResponse | null`、`metas: FactorMeta[]`（当前勾选）
- 上方主图容器：`ref` 挂 chart；蜡烛或收盘折线 + 所有 `plot==="overlay"` 的 outputs 折线（BOLL 三线）
- 下方：每个 `plot==="panel"` 因子一个独立 chart div（高度约 120px）
- 用 `chart.timeScale().subscribeVisibleLogicalRangeChange` 把主图 range 同步到副图（副图同样回写可选；一期至少主→副）
- `date` 转 `UTCTimestamp`：与 StockChart 日线一致（`new Date(date).getTime()/1000` 或项目既有 helper）
- MACD：`macd_hist` 用 HistogramSeries，另两条 LineSeries
- 无 data：显示错误/空状态文案，不 createChart

- [ ] **Step 3: 重写 Factors.tsx 布局**

```tsx
// 结构示意
<div className="grid gap-4 lg:grid-cols-[240px_1fr]">
  <FactorCatalog ... />
  <div className="space-y-3">
    <div className="flex flex-wrap gap-2 items-center">
      <SymbolSearchField value={symbol} onChange={setSymbol} />
      <select value={range} onChange={...}>近3月 / 近1年</select>
      <Button onPress={load}>计算</Button>
      {engine && <span className="text-xs">engine: {engine}</span>}
    </div>
    {error && <p className="text-sm text-red-600">{error}</p>}
    <FactorCharts data={series} metas={selectedMetas} />
  </div>
</div>
{/* 下方保留原 ML 模型 JSON + 对比训练卡片，避免删功能 */}
```

数据流：

1. mount：`api<{factors: FactorMeta[]}>("/api/factors")`，`selected` 初始化为 `default_enabled` 的 name
2. `load`：`api(`/api/factors/series?symbol=&names=${[...selected].join(",")}&start=&end=`)`
3. 勾选变化：debounce 300ms 自动 `load`（或仅点「计算」——一期用 **勾选 debounce 自动刷新**，与 spec 一致）
4. 解析 `start/end`：近 3M / 1Y 用本地日期字符串 `YYYY-MM-DD`

- [ ] **Step 4: 类型检查与前端单测**

Run:

```bash
cd apps/web && npm test -- src/factors/groupFactors.test.ts
cd apps/web && npx tsc -b --pretty false
```

Expected: 测试 PASS；`tsc` 无新增错误

- [ ] **Step 5: 手工验收清单（不后台启动服务；由执行者在已有进程或自行前台启动后点）**

1. `/factors` 左右布局
2. 已选常显、未选分类折叠
3. 默认勾选一期名单；主图有 SMA/BOLL，副图有 RSI/MACD 等
4. 无日线标的提示「无本地日线」
5. ML 区块仍在下方可用

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/factors apps/web/src/pages/Factors.tsx
git commit -m "feat(web): 因子页左目录右主副图展示"
```

---

## Spec Coverage（自检）

| Spec 要求 | Task |
| --- | --- |
| FactorRegistry 字段与默认名单 | Task 1 |
| desk_indicators 扩展 + 未知名 | Task 2 |
| compute_series / engine | Task 3 |
| GET /api/factors、/series、无日线 400 | Task 4 |
| 左栏已选常显、未选折叠 | Task 5–6 |
| 主图 overlay + panel 副图、lightweight-charts | Task 6 |
| 副图约 6 上限 | Task 6 |
| 复用 SymbolSearchField | Task 6 |
| Registry/series 单测 | Task 1–4 |
| 一期不改自定义 params | 全程未做参数 UI |
| 保留 ML 对比（非目标外兼容） | Task 6 下方保留 |

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-07-21-talib-factors-charts.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每任务新开子代理，任务间复审，迭代快  
2. **Inline Execution** — 本会话按 executing-plans 连续执行，设检查点  

选哪种？
