# 分时副图「资金趋势」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分时常驻第四副图「资金趋势」：主力进/撤、大盘资金进/撤、趋势线及准备/买入/逃顶等信号；指数按沪/深自动映射。

**Architecture:** 纯函数模块算公式（个股+指数对齐）；`StockDetailView` 拉指数分钟预热；`StockChart.addFundFlowPane` 用 Histogram/Bar/Line/markers 绘制，并重分配 scaleMargins/高度。

**Tech Stack:** React 19、TypeScript、Vitest、lightweight-charts 5、现有 `buildEmaSeries` / `toIntradayChartTime` / `sessionDateFromBars` / `loadMinuteBarsRange`。

**Spec:** `docs/superpowers/specs/2026-08-01-intraday-fund-flow-pane-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `apps/web/src/stock/indexSymbol.ts` | 标的 → 指数代码 |
| `apps/web/src/stock/indexSymbol.test.ts` | 单测 |
| `apps/web/src/stock/tdxMath.ts` | SMA(M=1)、HHV/LLV、REF、FILTER |
| `apps/web/src/stock/tdxMath.test.ts` | 单测 |
| `apps/web/src/stock/intradayFundFlow.ts` | `buildIntradayFundFlow` 产出 |
| `apps/web/src/stock/intradayFundFlow.test.ts` | 公式单测 |
| `apps/web/src/stock/StockChart.tsx` | 第四 pane + 高度/margins |
| `apps/web/src/stock/StockDetailView.tsx` | 拉指数 bars 并传入 |

---

### Task 1: `resolveIndexSymbol`（TDD）

**Files:**
- Create: `apps/web/src/stock/indexSymbol.ts`
- Create: `apps/web/src/stock/indexSymbol.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest";
import { resolveIndexSymbol } from "./indexSymbol";

describe("resolveIndexSymbol", () => {
  it("maps SH to SSE composite", () => {
    expect(resolveIndexSymbol("600519.SH")).toBe("000001.SH");
    expect(resolveIndexSymbol("688981.SH")).toBe("000001.SH");
  });

  it("maps SZ (incl. ChiNext) to SZSE component", () => {
    expect(resolveIndexSymbol("000001.SZ")).toBe("399001.SZ");
    expect(resolveIndexSymbol("300750.SZ")).toBe("399001.SZ");
  });

  it("returns null for unknown suffix", () => {
    expect(resolveIndexSymbol("FOO")).toBeNull();
  });
});
```

- [ ] **Step 2: 跑测确认失败**

```bash
cd apps/web && pnpm exec vitest run src/stock/indexSymbol.test.ts
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```typescript
/**
 * 按标的市场解析通达信 INDEX 所用大盘指数代码。
 * @param stockSymbol 如 600519.SH
 * @returns 000001.SH / 399001.SZ；无法识别则 null
 */
export function resolveIndexSymbol(stockSymbol: string): string | null {
  const sym = stockSymbol.trim().toUpperCase();
  if (sym.endsWith(".SH")) return "000001.SH";
  if (sym.endsWith(".SZ")) return "399001.SZ";
  return null;
}
```

- [ ] **Step 4: 跑测通过并 Commit**

```bash
pnpm exec vitest run src/stock/indexSymbol.test.ts
git add apps/web/src/stock/indexSymbol.ts apps/web/src/stock/indexSymbol.test.ts
git commit -m "feat(web): 分时资金趋势指数代码映射"
```

---

### Task 2: 通达信数学辅助（TDD）

**Files:**
- Create: `apps/web/src/stock/tdxMath.ts`
- Create: `apps/web/src/stock/tdxMath.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest";
import { smaTdx, hhv, llv, refAt, filterSignal } from "./tdxMath";

describe("smaTdx", () => {
  it("uses recursive Y=(X+(N-1)*Yprev)/N", () => {
    // N=3, M=1: y0=x0; y1=(x1+2*y0)/3; y2=(x2+2*y1)/3
    const y = smaTdx([3, 6, 9], 3);
    expect(y[0]).toBeCloseTo(3, 8);
    expect(y[1]).toBeCloseTo((6 + 2 * 3) / 3, 8);
    expect(y[2]).toBeCloseTo((9 + 2 * y[1]) / 3, 8);
  });
});

describe("hhv/llv", () => {
  it("rolling max/min over window", () => {
    expect(hhv([1, 3, 2, 5], 2)).toEqual([1, 3, 3, 5]);
    expect(llv([1, 3, 2, 5], 2)).toEqual([1, 1, 2, 2]);
  });
});

describe("refAt", () => {
  it("looks back N bars", () => {
    expect(refAt([10, 20, 30], 2, 1)).toBe(20);
    expect(refAt([10, 20, 30], 0, 1)).toBeNull();
  });
});

describe("filterSignal", () => {
  it("suppresses repeats within N bars", () => {
    const cond = [false, true, true, false, true];
    // N=2: fire at i=1, suppress i=2, fire at i=4
    expect(filterSignal(cond, 2)).toEqual([false, true, false, false, true]);
  });
});
```

- [ ] **Step 2: 跑测 FAIL → 实现 → PASS**

实现要点：

```typescript
/** 通达信 SMA(X,N,1)。N<1 返回全 NaN 或空由调用方避免。 */
export function smaTdx(values: number[], n: number): number[] { /* ... */ }

/** 滚动最高；窗口不足时用已有前缀。 */
export function hhv(values: number[], n: number): number[] { /* ... */ }

export function llv(values: number[], n: number): number[] { /* ... */ }

/** REF(X,N) 在下标 i；越界 null */
export function refAt(values: number[], i: number, n: number): number | null { /* ... */ }

/**
 * FILTER(cond,N)：cond 为真时输出真，随后 N 根内忽略。
 * @param cond 条件序列
 * @param n 抑制根数（通达信 FILTER 第二参数）
 */
export function filterSignal(cond: boolean[], n: number): boolean[] { /* ... */ }
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(web): 通达信 SMA/HHV/LLV/FILTER 辅助函数"
```

---

### Task 3: `buildIntradayFundFlow`（TDD）

**Files:**
- Create: `apps/web/src/stock/intradayFundFlow.ts`
- Create: `apps/web/src/stock/intradayFundFlow.test.ts`

- [ ] **Step 1: 定义产出类型与 API**

```typescript
import type { Time } from "lightweight-charts";
import type { OhlcvBar } from "./types";

export type FundFlowHist = {
  time: Time;
  value: number;
  color: string;
};

export type FundFlowStick = {
  time: Time;
  low: number;
  high: number;
  color: string;
};

export type FundFlowMarker = {
  time: Time;
  price: number;
  text: string;
  color: string;
};

export type FundFlowBuildResult = {
  /** 主力进/撤、大盘进/撤 等柱 */
  hists: FundFlowHist[];
  lines: Array<{ label: string; color: string; points: Array<{ time: Time; value: number }> }>;
  sticks: FundFlowStick[];
  markers: FundFlowMarker[];
};

export type FundFlowBuildInput = {
  /** 含预热的个股分钟线 */
  stockBars: OhlcvBar[];
  /** 含预热的指数分钟线（可空） */
  indexBars: OhlcvBar[];
  /** 当天 YYYY-MM-DD */
  sessionDate: string;
};

/**
 * 构建分时「资金趋势」副图数据（T=1）。
 * @param input 个股/指数分钟与会话日
 */
export function buildIntradayFundFlow(input: FundFlowBuildInput): FundFlowBuildResult;
```

- [ ] **Step 2: 写失败测试（核心）**

```typescript
describe("buildIntradayFundFlow", () => {
  it("builds trend line and main-force hist without index", () => {
    // 构造 ≥60 根单调分钟（跨昨今两日），sessionDate=今日
    // 断言：lines 含「趋势线」且末点有限；hists 含品红或蓝色点
  });

  it("adds index fund hists when indexBars align", () => {
    // 同分钟 ts 的指数 bars；断言出现红/绿大盘柱之一（或长度为当天点数级）
  });

  it("does not throw when indexBars empty", () => {
    expect(() =>
      buildIntradayFundFlow({ stockBars: fixture, indexBars: [], sessionDate })
    ).not.toThrow();
  });
});
```

（fixture 具体数值由实现者按「≥60 根、有 OHLC」写满，末值用 `toBeFinite` 即可，不必锁死通达信平台浮点。）

- [ ] **Step 3: 实现计算流程**

1. 过滤/排序 `stockBars`、`indexBars`（有 `ts`）。
2. 建 `Map<beijingMinuteKey, indexBar>`：key = `beijingDateFromTs + hour:minute` 或会话内用 `toIntradayChartTime` 仅对当日；**预热日**用 `date+HH:mm` 字符串对齐。
3. 对每个 stock bar 取 close/high/low；若有对齐 index 取 INDEXC/H/L，否则 index 分量记 `null`。
4. 全序列算 V1…V4、趋势线、V12（有 index 时算 VB）；用 `buildEmaSeries` 时先把 values 填进临时 `ChartBar[]`（顺序 unix time），或对 number[] 写本地 `emaValues(values, n)`。
5. 仅 `beijingDateFromTs === sessionDate` 且 `toIntradayChartTime` 非空的点输出到结果。
6. 信号：
   - `准备`: `filterSignal(trend<=13, 15)` → stick 0–8 `#CC9900` + marker「准备」@20
   - `买入`: `filterSignal(trend<=13 && V12>13, 10)` → stick 0–16 `#0099FF` + marker「买入」@5 黄
   - `卖临界`: `trend>90 && trend>ref(trend,1)` → stick 100–95 `#FFFF00`
   - `逃顶`: `filterSignal(trend>90 && trend<ref && 主力进<ref(主力进), 8)` → marker「逃顶」@90
   - 条件加强柱按规格颜色与 0–30 / 0–40

颜色常量集中在文件顶部。

- [ ] **Step 4: 跑测 PASS + Commit**

```bash
pnpm exec vitest run src/stock/intradayFundFlow.test.ts src/stock/tdxMath.test.ts
git commit -m "feat(web): 分时资金趋势副图公式计算"
```

---

### Task 4: `StockChart` 第四 pane

**Files:**
- Modify: `apps/web/src/stock/StockChart.tsx`

- [ ] **Step 1: 扩展 props**

```typescript
/** 指数分钟线（含预热）；分时资金趋势用 */
indexBars?: OhlcvBar[];
```

- [ ] **Step 2: 调整高度与 margins（分时 + MACD 时）**

目标分区（逻辑比例，可微调）：

- 主图 scaleMargins：`{ top: 0.04, bottom: 0.52 }`
- volume：`{ top: 0.52, bottom: 0.38 }`
- macd：`{ top: 0.66, bottom: 0.22 }`
- fund：`{ top: 0.82, bottom: 0 }`

容器高度：`showMacd` 时 compact `360` / 默认 `480`（原 300/400）。

`addVolumePane` / `addMacdPane` 增加参数或读取「是否有 fund pane」以改 margins；分时恒有 fund → `withFundFlow=true`。

- [ ] **Step 3: `addFundFlowPane`**

```typescript
function addFundFlowPane(
  chart: IChartApi,
  stockBars: OhlcvBar[],
  indexBars: OhlcvBar[] | undefined,
  sessionDate: string | undefined
): void {
  if (!sessionDate) return;
  const built = buildIntradayFundFlow({
    stockBars,
    indexBars: indexBars ?? [],
    sessionDate,
  });
  // HistogramSeries priceScaleId: "fund" — 主力/大盘柱（可按 color 拆多个 series）
  // LineSeries 趋势线
  // BarSeries sticks
  // createSeriesMarkers 挂在趋势线 series 上
}
```

在分时分支：volume → macd → **fund**（`overlayCalcBars` 预热个股若存在则优先作 stockBars 输入，否则 `bars`）。

```typescript
const stockForFund =
  overlayCalcBars && overlayCalcBars.length > 0 ? overlayCalcBars : bars;
addFundFlowPane(chart, stockForFund, indexBars, sessionDate);
```

- [ ] **Step 4: deps 加入 `indexBars`；跑 `pnpm exec vitest run src/stock/`；Commit**

```bash
git commit -m "feat(web): 分时图绘制资金趋势副图"
```

---

### Task 5: `StockDetailView` 拉指数

**Files:**
- Modify: `apps/web/src/stock/StockDetailView.tsx`

- [ ] **Step 1: 状态与 effect**

```typescript
const [indexBars, setIndexBars] = useState<OhlcvBar[]>([]);

useEffect(() => {
  if (period !== "intraday") {
    setIndexBars([]);
    return;
  }
  const indexSym = resolveIndexSymbol(normalizedSymbol);
  if (!indexSym) {
    setIndexBars([]);
    return;
  }
  let cancelled = false;
  const load = async () => {
    const toDate = intradaySessionDate ?? beijingToday();
    const fromDate = shiftTradingDaysBack(toDate, 5);
    try {
      const data = await loadMinuteBarsRange(indexSym, fromDate, toDate);
      if (!cancelled) setIndexBars(data);
    } catch {
      if (!cancelled) setIndexBars([]);
    }
  };
  void load();
  return () => {
    cancelled = true;
  };
}, [normalizedSymbol, period, reloadKey, intradaySessionDate]);
```

- [ ] **Step 2: 传给 StockChart**

```tsx
indexBars={period === "intraday" ? indexBars : undefined}
```

个股预热：资金趋势已用 `overlayCalcBars` 或当日 `bars`；可选在分时时**始终**拉 5 日个股分钟供 fund/EMA（若 `overlayCalcBars` 仅在 dip 时有值，则另加 `fundCalcBars` 或复用同一 5 日拉取）。

**必须：** 分时无论是否选「分时抄底」，都要有 ≥55 根预热个股分钟。做法二选一（推荐 A）：

- **A.** 抽取 `loadWarmupMinuteBars(symbol)`，`intraday_dip` 与资金趋势共用同一 state `warmupBars`（原 `overlayCalcBars` 可改名或并行赋值）。
- **B.** 资金趋势单独再拉一次 5 日个股（简单但多一次请求）。

本任务采用 **A**：将现有 dip 的 5 日拉取提升为「分时即拉」`warmupBars`，dip 与 fund 共用；`overlayCalcBars={warmupBars}`，`buildIntradayFundFlow` 的 stockBars 亦用 `warmupBars`（空则退回 `bars`）。

- [ ] **Step 3: 测试 + Commit**

```bash
pnpm exec vitest run src/stock/
git commit -m "feat(web): 分时加载指数分钟供资金趋势副图"
```

---

### Task 6: 规格收尾

**Files:**
- Modify: `docs/superpowers/specs/2026-08-01-intraday-fund-flow-pane-design.md`（状态 → 已实现）

- [ ] **Step 1: 改状态并 Commit**

```bash
git commit -m "docs: 分时资金趋势副图规格标为已实现"
```

---

## Spec coverage

| 规格项 | Task |
|--------|------|
| 指数映射 | T1 |
| SMA/FILTER/HHV | T2 |
| 完整公式绘制数据 | T3 |
| 第四 pane / margins | T4 |
| 拉指数 + 共用预热 | T5 |
| 文档状态 | T6 |

## Placeholder scan

无 TBD；fixture「由实现者写满」仅限测试数据形状，断言标准已写明（`toBeFinite` / 颜色存在）。

## Type consistency

- `FundFlowBuildResult` / `FundFlowBuildInput` 贯穿 T3–T5
- props：`indexBars`、`sessionDate`、`overlayCalcBars`/`warmupBars` 命名在 T5 统一为：对外仍传 `indexBars`；预热个股 state 名 `warmupBars`，并同时作为 dip 的 `overlayCalcBars`
