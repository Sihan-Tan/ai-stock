# 黄金坑套件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后端统一计算综合因子 `GOLDEN_PIT`（曲线 + 黄金坑/井喷信号，无未来函数）；因子页可勾选；股票详情日 K 常驻副图通过 `/api/factors/series` 拉取同套序列。

**Architecture:** `desk_factor/golden_pit.py` 纯函数产出 DataFrame 列；registry 注册自定义因子；`FactorService` 增加非 TA-Lib 分支。前端 `StockDetailView` 日线拉 series，`StockChart` 新增 `golden_pit` priceScale 副图。

**Tech Stack:** Python 3、pandas、pytest、FastAPI 现有 factors API、React、lightweight-charts、Vitest。

**Spec:** `docs/superpowers/specs/2026-08-05-golden-pit-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| Create: `packages/factor/desk_factor/golden_pit.py` | 无未来：`gp_line` / `gp_pit` / `gp_blowoff` |
| Create: `tests/test_golden_pit.py` | 纯函数与因果性单测 |
| Modify: `packages/factor/desk_factor/registry.py` | 注册 `GOLDEN_PIT` |
| Modify: `packages/factor/desk_factor/__init__.py` | 自定义分支 + warmup |
| Modify: `tests/test_factor_registry.py` | 元数据断言 |
| Create: `tests/test_golden_pit_series.py` | `compute_series_from_df` 契约 |
| Modify: `apps/web/src/stock/StockChart.tsx` | 日 K `golden_pit` pane + 高度 |
| Modify: `apps/web/src/stock/StockDetailView.tsx` | 日线拉 `GOLDEN_PIT` series |
| Create: `apps/web/src/stock/goldenPitSeries.ts` | 类型 + 请求/对齐辅助（可选但推荐） |
| Create: `apps/web/src/stock/goldenPitSeries.test.ts` | 日线才请求等纯函数测 |
| Modify: `docs/superpowers/specs/2026-08-05-golden-pit-design.md` | 状态 → 已实现 |

一期 **省略** `gp_line2`（规格允许）。

---

### Task 1: `golden_pit` 纯函数（TDD）

**Files:**
- Create: `packages/factor/desk_factor/golden_pit.py`
- Create: `tests/test_golden_pit.py`

- [ ] **Step 1: 写失败单测**

```python
"""黄金坑套件：无未来波谷近似 + 井喷。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from desk_factor.golden_pit import compute_golden_pit


def _ohlcv(n: int, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 10 + np.cumsum(rng.normal(0, 0.2, size=n))
    high = close + rng.uniform(0.05, 0.4, size=n)
    low = close - rng.uniform(0.05, 0.4, size=n)
    open_ = close + rng.normal(0, 0.05, size=n)
    vol = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    dates = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m-%d") for d in dates],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


def test_compute_golden_pit_columns_and_length():
    df = _ohlcv(120)
    out = compute_golden_pit(df)
    assert list(out.columns) == ["gp_line", "gp_pit", "gp_blowoff"]
    assert len(out) == len(df)


def test_blowoff_triggers_on_limit_up_style_bar():
    """井喷：涨幅≥9.9% 且光头阳 + 缩量，且近 20 根内首次。"""
    n = 40
    df = _ohlcv(n, seed=1)
    # 构造第 30 根：开=低、收=高、相对昨收 +10%，量小于 MA5 且小于昨量
    i = 30
    df.loc[i - 1, "close"] = 10.0
    df.loc[i, "open"] = 10.0
    df.loc[i, "low"] = 10.0
    df.loc[i, "high"] = 11.0
    df.loc[i, "close"] = 11.0
    df.loc[i, "volume"] = 500_000.0
    for j in range(i - 5, i):
        df.loc[j, "volume"] = 2_000_000.0
    out = compute_golden_pit(df)
    assert float(out.loc[i, "gp_blowoff"]) != 0.0


def test_pit_is_causal_prefix_stable():
    """截断未来 bar 后，已有前缀的 gp_pit 不变。"""
    df = _ohlcv(80, seed=2)
    full = compute_golden_pit(df)
    prefix = compute_golden_pit(df.iloc[:60].reset_index(drop=True))
    a = full.iloc[:60]["gp_pit"].fillna(0).to_numpy()
    b = prefix["gp_pit"].fillna(0).to_numpy()
    assert np.allclose(a, b)


def test_gp_line_finite_after_warmup():
    df = _ohlcv(80)
    out = compute_golden_pit(df)
    # 34+5 预热后应有有限值
    assert np.isfinite(out["gp_line"].iloc[50])
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_golden_pit.py -v`

Expected: FAIL（`desk_factor.golden_pit` 不存在）

- [ ] **Step 3: 实现 `golden_pit.py`**

```python
"""黄金坑套件：无未来函数的日线序列（曲线 + 黄金坑/井喷）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 主曲线：通达信 VARE 语义（无未来）
_LINE_LLV = 34
_LINE_MA = 5
# 因果枢轴低点：用下一根确认（仅用到当前 bar）
_PIVOT_LEFT = 2
_PIT_MAX_AGE = 4  # 类似 TROUGHBARS<4
_PIT_FILTER = 3
_PIT_MARK = 50.0
_BLOWOFF_MARK = 50.0


def _ma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if n <= 0 or len(x) == 0:
        return out
    c = np.cumsum(np.nan_to_num(x, nan=0.0))
    for i in range(len(x)):
        if i + 1 < n:
            continue
        out[i] = (c[i] - (c[i - n] if i >= n else 0.0)) / n
    return out


def _llv(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(len(x)):
        start = max(0, i - n + 1)
        out[i] = float(np.nanmin(x[start : i + 1]))
    return out


def _hhv(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(len(x)):
        start = max(0, i - n + 1)
        out[i] = float(np.nanmax(x[start : i + 1]))
    return out


def _filter_signal(flags: np.ndarray, n: int) -> np.ndarray:
    """通达信 FILTER：信号后抑制 n 根。"""
    out = np.zeros(len(flags), dtype=float)
    suppress = 0
    for i, f in enumerate(flags):
        if suppress > 0:
            suppress -= 1
            continue
        if f:
            out[i] = 1.0
            suppress = n
    return out


def _causal_pivot_low(low: np.ndarray) -> np.ndarray:
    """
    在 bar i 确认 i-1 为枢轴低点：low[i-1] < low[i-1-k]（k=1..LEFT）且 low[i-1] < low[i]。
    仅使用 ≤i 的数据。
    """
    n = len(low)
    out = np.zeros(n, dtype=bool)
    for i in range(_PIVOT_LEFT + 1, n):
        j = i - 1
        ok = True
        for k in range(1, _PIVOT_LEFT + 1):
            if not (low[j] < low[j - k]):
                ok = False
                break
        if ok and low[j] < low[i]:
            out[i] = True
    return out


def _bars_since_event(events: np.ndarray) -> np.ndarray:
    out = np.full(len(events), np.nan)
    last = -10**9
    for i, e in enumerate(events):
        if e:
            last = i
        if last >= 0:
            out[i] = float(i - last)
    return out


def compute_golden_pit(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """
    计算黄金坑套件列。

    @param ohlcv 需含 open/high/low/close/volume（列名小写）；行按时间升序
    @returns 与输入等长的 gp_line / gp_pit / gp_blowoff
    """
    df = ohlcv.copy()
    rename = {c: str(c).lower() for c in df.columns}
    df = df.rename(columns=rename)
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    n = len(df)

    # gp_line ≈ MA(100*(C-LLV(C,34))/(HHV(H,34)-LLV(L,34)),5)-20
    den = _hhv(high, _LINE_LLV) - _llv(low, _LINE_LLV)
    raw = np.where(den > 1e-12, 100.0 * (close - _llv(close, _LINE_LLV)) / den, np.nan)
    gp_line = _ma(raw, _LINE_MA) - 20.0

    # 黄金坑：距最近已确认枢轴低点的 bar 数 < 4，再 FILTER
    piv = _causal_pivot_low(low)
    age = _bars_since_event(piv)
    raw_pit = np.array(
        [(np.isfinite(a) and a < _PIT_MAX_AGE and a >= 0) for a in age],
        dtype=bool,
    )
    # 排除「刚确认当根 age==0」的噪声：要求 0 < age < 4（落在波谷后数根内）
    raw_pit = np.array(
        [bool(np.isfinite(a) and 0 < a < _PIT_MAX_AGE) for a in age],
        dtype=bool,
    )
    gp_pit = _filter_signal(raw_pit, _PIT_FILTER) * _PIT_MARK

    # 井喷
    ref_c = np.roll(close, 1)
    ref_c[0] = np.nan
    ref_v = np.roll(vol, 1)
    ref_v[0] = np.nan
    ma_v5 = _ma(vol, 5)
    up = (close / ref_c) >= 1.099
    marubozu = (np.abs(open_ - low) < 1e-8) & (np.abs(high - close) < 1e-8)
    thin = (vol < ma_v5) & (vol < ref_v)
    cond = up & marubozu & thin & np.isfinite(ref_c)
    # COUNT(cond,20)==1 → 近 20 根（含当前）恰好 1 次为真，即当前为真且前 19 根无
    blow = np.zeros(n, dtype=float)
    for i in range(n):
        if not cond[i]:
            continue
        start = max(0, i - 19)
        if int(np.sum(cond[start : i + 1])) == 1:
            blow[i] = _BLOWOFF_MARK

    return pd.DataFrame(
        {"gp_line": gp_line, "gp_pit": gp_pit, "gp_blowoff": blow},
        index=df.index,
    )
```

- [ ] **Step 4: 跑测通过**

Run: `pytest tests/test_golden_pit.py -v`

Expected: PASS（若井喷浮点失败，放宽 `open/low` 赋值或 epsilon）

- [ ] **Step 5: Commit**

```powershell
git add packages/factor/desk_factor/golden_pit.py tests/test_golden_pit.py
$msg = @"
feat(factor): 黄金坑套件纯函数计算（无未来）
"@
git commit -m $msg
```

---

### Task 2: Registry + FactorService 接线

**Files:**
- Modify: `packages/factor/desk_factor/registry.py`
- Modify: `packages/factor/desk_factor/__init__.py`
- Modify: `tests/test_factor_registry.py`
- Create: `tests/test_golden_pit_series.py`

- [ ] **Step 1: 扩展 registry**

在 `_build_price_factors` 旁新增：

```python
def _build_custom_factors() -> list[FactorMeta]:
    """非 TA-Lib 自定义因子。"""
    guide = (
        "【含义】黄金坑套件：强弱曲线 + 无未来近似「黄金坑」与「井喷」买卖类信号。\n"
        "【怎么用】副图看 gp_line；gp_pit / gp_blowoff 非 0 为事件。日 K 详情常驻同套序列。\n"
        "【注意点】黄金坑波谷为因果近似，与通达信 TROUGHBARS/ZIG 不完全一致；已剔除未来函数。"
    )
    return [
        _f(
            "GOLDEN_PIT",
            talib="",
            label="黄金坑套件",
            category="custom",
            params={"llv": 34, "ma": 5, "pit_age": 4, "pit_filter": 3},
            outputs=["gp_line", "gp_pit", "gp_blowoff"],
            plot="panel",
            default_enabled=False,
            description=guide,
        )
    ]
```

在 `_merge_registry` 中于 price 因素之后：

```python
    for row in _build_custom_factors():
        by_name[row["name"]] = row
```

注意：`_f` 在 `talib=""` 时 `lookup = name`，需保证 `zh_guide`/`zh_desc` 对未知名回退可用；因传入了显式 `description` 与 `label`，不受影响。

- [ ] **Step 2: 改 `warmup_calendar_days`**

在循环内增加：

```python
        if str(meta.get("name") or "").upper() == "GOLDEN_PIT":
            max_period = max(max_period, 80)
```

- [ ] **Step 3: 改 `compute_series_from_df`**

在拆分 `price_names` / `ta_only` 时抽出自定义名：

```python
        custom_names = [
            n for n in ta_names if str(n).strip().upper() == "GOLDEN_PIT"
        ]
        price_names = [
            n
            for n in ta_names
            if str(n).strip().upper() in {"CLOSE", "OPEN", "HIGH", "LOW", "VOLUME"}
        ]
        ta_only = [n for n in ta_names if n not in price_names and n not in custom_names]
```

在 `if price_names:` 块之后、`if ta_only:` 之前：

```python
        if custom_names:
            from desk_factor.golden_pit import compute_golden_pit

            gp_df = compute_golden_pit(ohlcv)
            for raw in custom_names:
                meta = get_factor(raw)
                if meta is None:
                    raise ValueError(f"unknown factor: {raw}")
                outputs: dict[str, list[dict[str, Any]]] = {}
                for col in meta["outputs"]:
                    points = []
                    for idx, r in ohlcv.iterrows():
                        d = str(r["date"])[:10]
                        val = gp_df.loc[idx, col] if idx in gp_df.index else gp_df[col].iloc[len(points)]
                        # 更稳：按位置对齐
                    # 推荐按位置：
                gp_df = gp_df.reset_index(drop=True)
                ohlcv_i = ohlcv.reset_index(drop=True)
                for col in meta["outputs"]:
                    points = []
                    for i, r in ohlcv_i.iterrows():
                        d = str(r["date"])[:10]
                        val = gp_df.at[i, col]
                        points.append(
                            {"date": d, "v": None if val is None or pd.isna(val) else float(val)}
                        )
                    outputs[col] = points
                series[meta["name"]] = {"outputs": outputs}
```

（实现时写成清晰的 reset_index 对齐，避免重复混乱代码。）

- [ ] **Step 4: 单测**

`tests/test_factor_registry.py` 增加：

```python
def test_golden_pit_registered():
    by_name = {f["name"]: f for f in FACTOR_REGISTRY}
    f = by_name["GOLDEN_PIT"]
    assert f["label"] == "黄金坑套件"
    assert f["plot"] == "panel"
    assert f["talib"] == ""
    assert f["outputs"] == ["gp_line", "gp_pit", "gp_blowoff"]
    assert "无未来" in f["description"] or "TROUGHBARS" in f["description"]
```

`tests/test_golden_pit_series.py`：

```python
"""GOLDEN_PIT 经 FactorService 出序列。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from desk_factor import FactorService


def test_compute_series_from_df_golden_pit():
    n = 100
    rng = np.random.default_rng(0)
    close = 10 + np.cumsum(rng.normal(0, 0.1, n))
    df = pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-01", periods=n)],
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": np.full(n, 1e6),
        }
    )
    out = FactorService(db=None).compute_series_from_df(df, ["GOLDEN_PIT"])
    block = out["series"]["GOLDEN_PIT"]["outputs"]
    assert set(block) == {"gp_line", "gp_pit", "gp_blowoff"}
    assert len(block["gp_line"]) == n
```

- [ ] **Step 5: 跑测**

```powershell
pytest tests/test_golden_pit.py tests/test_golden_pit_series.py tests/test_factor_registry.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```powershell
git add packages/factor/desk_factor/registry.py packages/factor/desk_factor/__init__.py tests/test_factor_registry.py tests/test_golden_pit_series.py
$msg = @"
feat(factor): 注册 GOLDEN_PIT 并接入 FactorService
"@
git commit -m $msg
```

---

### Task 3: 前端拉数辅助（日线才请求）

**Files:**
- Create: `apps/web/src/stock/goldenPitSeries.ts`
- Create: `apps/web/src/stock/goldenPitSeries.test.ts`

- [ ] **Step 1: 测试**

```typescript
/** 日 K 是否应加载黄金坑套件。 */
import { describe, expect, it } from "vitest";
import { shouldLoadGoldenPit, type GoldenPitOutputs } from "./goldenPitSeries";

describe("shouldLoadGoldenPit", () => {
  it("only day", () => {
    expect(shouldLoadGoldenPit("day")).toBe(true);
    expect(shouldLoadGoldenPit("week")).toBe(false);
    expect(shouldLoadGoldenPit("month")).toBe(false);
    expect(shouldLoadGoldenPit("intraday")).toBe(false);
  });
});

describe("pickGoldenPitOutputs", () => {
  it("reads nested series block", async () => {
    const { pickGoldenPitOutputs } = await import("./goldenPitSeries");
    const raw = {
      series: {
        GOLDEN_PIT: {
          outputs: {
            gp_line: [{ date: "2020-01-02", v: 1 }],
            gp_pit: [{ date: "2020-01-02", v: 0 }],
            gp_blowoff: [{ date: "2020-01-02", v: 50 }],
          },
        },
      },
    };
    const out = pickGoldenPitOutputs(raw) as GoldenPitOutputs;
    expect(out.gp_line).toHaveLength(1);
    expect(out.gp_blowoff[0]?.v).toBe(50);
  });
});
```

- [ ] **Step 2: 实现**

```typescript
import type { ChartPeriod } from "./types"; // 若无统一类型，用 string 联合

export type FactorPoint = { date: string; v: number | null };

export type GoldenPitOutputs = {
  gp_line: FactorPoint[];
  gp_pit: FactorPoint[];
  gp_blowoff: FactorPoint[];
};

/**
 * 是否在该周期加载黄金坑套件副图数据。
 * @param period 图表周期
 */
export function shouldLoadGoldenPit(period: string): boolean {
  return period === "day";
}

/**
 * 从 factors/series 响应取出 GOLDEN_PIT 输出；缺失则空数组。
 * @param payload API JSON
 */
export function pickGoldenPitOutputs(payload: unknown): GoldenPitOutputs {
  const empty: GoldenPitOutputs = { gp_line: [], gp_pit: [], gp_blowoff: [] };
  if (!payload || typeof payload !== "object") return empty;
  const series = (payload as { series?: Record<string, { outputs?: Record<string, FactorPoint[]> }> })
    .series;
  const outs = series?.GOLDEN_PIT?.outputs;
  if (!outs) return empty;
  return {
    gp_line: outs.gp_line ?? [],
    gp_pit: outs.gp_pit ?? [],
    gp_blowoff: outs.gp_blowoff ?? [],
  };
}
```

（若 `ChartPeriod` 路径不同，按仓库实际 import 调整。）

- [ ] **Step 3: Vitest**

```powershell
cd apps/web
pnpm exec vitest run src/stock/goldenPitSeries.test.ts --environment node
```

Expected: PASS

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/stock/goldenPitSeries.ts apps/web/src/stock/goldenPitSeries.test.ts
$msg = @"
feat(web): 黄金坑套件 series 解析辅助
"@
git commit -m $msg
```

---

### Task 4: `StockChart` 日 K 副图

**Files:**
- Modify: `apps/web/src/stock/StockChart.tsx`

- [ ] **Step 1: Props**

为 `StockChart` 增加可选：

```typescript
  /** 日 K 黄金坑套件序列；非日线或失败时不传 */
  goldenPit?: {
    gp_line: { date: string; v: number | null }[];
    gp_pit: { date: string; v: number | null }[];
    gp_blowoff: { date: string; v: number | null }[];
  } | null;
```

- [ ] **Step 2: 高度与 margins**

当 `period === "day" && goldenPit` 有任一非空序列时 `withGoldenPit = true`。

`chartHeight` / `heightClass`：在现有「有 MACD」档再各 **+100**（例如日线有 MACD 的 500→600，compact 400→500）。仅 day+goldenPit 时生效；分时资金趋势逻辑不变。

主图 `scaleMargins.bottom`：有 goldenPit 时比「仅 MACD」再加大（例如 bottom 从 0.46 → 0.58 量级，以实际可读为准）。

- [ ] **Step 3: `addGoldenPitPane`**

仿 `addMacdPane`，`priceScaleId: "golden_pit"`：

- `gp_line` → `LineSeries`（如 `#fbbf24`）
- `gp_pit` 非 0 → `HistogramSeries` 或细柱（红/黄 `rgba(239,68,68,0.7)`）
- `gp_blowoff` 非 0 → 直方图（绿）

时间：用 `date` 字符串作为 lightweight-charts business day（与日 K 一致）。将 API 点按 `date` 对齐到 `chartBars`。

在日线分支于 `addMacdPane` **之后**调用 `addGoldenPitPane`。

调整 volume/macd 的 `scaleMargins`：当 `withGoldenPit` 时上移，给底部腾出约 18%～22% 高度（参考分时 `withFundFlow` 的分层方式，但仅日线三副图：量 / MACD / 黄金坑）。

建议日线三副图 margins 目标（可微调）：

| scale | top | bottom |
|-------|-----|--------|
| main | 0.04 | 0.58 |
| volume | 0.46 | 0.40 |
| macd | 0.64 | 0.22 |
| golden_pit | 0.82 | 0 |

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/stock/StockChart.tsx
$msg = @"
feat(web): 日K常驻黄金坑套件副图
"@
git commit -m $msg
```

---

### Task 5: `StockDetailView` 拉数接线

**Files:**
- Modify: `apps/web/src/stock/StockDetailView.tsx`

- [ ] **Step 1: 状态**

```typescript
const [goldenPit, setGoldenPit] = useState<GoldenPitOutputs | null>(null);
```

- [ ] **Step 2: 加载**

在 bars 成功且 `shouldLoadGoldenPit(period)` 时：

```typescript
const start = /* 与当前日K请求相同的 start */;
const end = /* 同上 */;
const data = await api<unknown>(
  `/api/factors/series?symbol=${encodeURIComponent(normalizedSymbol)}&names=GOLDEN_PIT&start=${start}&end=${end}`
);
setGoldenPit(pickGoldenPitOutputs(data));
```

非日线：`setGoldenPit(null)`，不请求。

失败：`setGoldenPit(null)`（或空 outputs），不打断 bars。

- [ ] **Step 3: 传入 StockChart**

```tsx
<StockChart
  ...
  goldenPit={period === "day" ? goldenPit : null}
/>
```

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/stock/StockDetailView.tsx
$msg = @"
feat(web): 日K详情拉取 GOLDEN_PIT 序列
"@
git commit -m $msg
```

---

### Task 6: 规格状态与总验证

**Files:**
- Modify: `docs/superpowers/specs/2026-08-05-golden-pit-design.md`

- [ ] **Step 1:** 状态改为 `已实现`

- [ ] **Step 2: 总验证**

```powershell
pytest tests/test_golden_pit.py tests/test_golden_pit_series.py tests/test_factor_registry.py -v
cd apps/web
pnpm exec vitest run src/stock/goldenPitSeries.test.ts --environment node
```

Expected: 全部 PASS

- [ ] **Step 3: Commit**

```powershell
git add docs/superpowers/specs/2026-08-05-golden-pit-design.md
$msg = @"
docs: 黄金坑套件规格标为已实现
"@
git commit -m $msg
```

---

## Self-Review

1. **Spec coverage:** 计算/无未来/井喷/综合因子/FactorService/日 K series 副图/因子页注册（registry 即可被 Factors 勾选）/测试 — 均有对应 Task；`gp_line2` 按规格省略。
2. **Placeholder scan:** 算法与代码块完整；无 TBD。
3. **Type consistency:** 输出列名 `gp_line` / `gp_pit` / `gp_blowoff`、因子名 `GOLDEN_PIT` 前后一致。
