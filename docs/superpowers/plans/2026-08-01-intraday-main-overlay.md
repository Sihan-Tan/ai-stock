# 分时主图指标（分时抄底）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分时工具条增加主图指标下拉（默认「无」），并叠加通达信「分时抄底」（色带 + 支撑/阻力 + 信号标记）；不改现有分时面积线与均价线。

**Architecture:** 扩展 `mainOverlays`：分时注册 `none` / `intraday_dip`；产出 `lines` + `sticks` + `markers`。计算用约 5 个交易日分钟线（按真实 `ts` 算 EMA，再裁当天映射到会话轴）；`StockChart` 在分时主图上用 BarSeries 近似 STICKLINE、`createSeriesMarkers` 画 ★。

**Tech Stack:** React 19、TypeScript、Vitest、lightweight-charts 5（`BarSeries`、`createSeriesMarkers`）、现有 `buildEmaSeries` / `toIntradayChartTime`。

**Spec:** `docs/superpowers/specs/2026-08-01-intraday-main-overlay-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `apps/web/src/stock/overlayMath.ts` | `crossUp` / `longCrossUp`、交易日回推、按北京日过滤 |
| `apps/web/src/stock/overlayMath.test.ts` | 上述纯函数单测 |
| `apps/web/src/stock/mainOverlays.ts` | 注册 `none` / `intraday_dip`；`buildIntradayDipOverlay`；兼容旧 `buildLines` |
| `apps/web/src/stock/mainOverlays.test.ts` | 注册表 + 分时抄底公式断言 |
| `apps/web/src/stock/StockChart.tsx` | 分时叠加 sticks / lines / markers |
| `apps/web/src/stock/StockDetailView.tsx` | 默认 `none`；分时拉 5 日计算 bars；传入 `preClose` |

---

### Task 1: 交叉与交易日辅助（TDD）

**Files:**
- Create: `apps/web/src/stock/overlayMath.ts`
- Create: `apps/web/src/stock/overlayMath.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest";
import {
  crossUp,
  longCrossUp,
  shiftTradingDaysBack,
  beijingDateFromTs,
  filterBarsOnBeijingDate,
} from "./overlayMath";
import type { OhlcvBar } from "./types";

describe("crossUp", () => {
  it("detects A crossing above B", () => {
    expect(crossUp([1, 1, 3], [2, 2, 2], 2)).toBe(true);
    expect(crossUp([1, 1, 1], [2, 2, 2], 2)).toBe(false);
    expect(crossUp([3, 3, 3], [2, 2, 2], 2)).toBe(false);
  });
});

describe("longCrossUp", () => {
  it("requires stay above for N bars after cross", () => {
    // i=2: 1→3 上穿 2；i=3 仍 > → LONGCROSS(...,2) 在 i=3 为 true
    expect(longCrossUp([1, 1, 3, 4], [2, 2, 2, 2], 3, 2)).toBe(true);
    expect(longCrossUp([1, 1, 3, 1], [2, 2, 2, 2], 3, 2)).toBe(false);
    expect(longCrossUp([1, 1, 3], [2, 2, 2], 2, 2)).toBe(false);
  });
});

describe("shiftTradingDaysBack", () => {
  it("skips weekends", () => {
    // 2026-07-27 周一；回推 1 个交易日 → 2026-07-24 周五
    expect(shiftTradingDaysBack("2026-07-27", 1)).toBe("2026-07-24");
    // 回推 5 个交易日：26=周日跳过… → 2026-07-20 周一
    expect(shiftTradingDaysBack("2026-07-27", 5)).toBe("2026-07-20");
  });
});

describe("filterBarsOnBeijingDate", () => {
  it("keeps bars on the given Beijing calendar day", () => {
    const bars: OhlcvBar[] = [
      {
        ts: "2026-07-27T09:31:00+08:00",
        open: 1,
        high: 1,
        low: 1,
        close: 1,
        volume: 1,
      },
      {
        ts: "2026-07-28T09:31:00+08:00",
        open: 2,
        high: 2,
        low: 2,
        close: 2,
        volume: 1,
      },
    ];
    expect(filterBarsOnBeijingDate(bars, "2026-07-27")).toHaveLength(1);
    expect(beijingDateFromTs("2026-07-27T15:00:00+08:00")).toBe("2026-07-27");
  });
});
```

- [ ] **Step 2: 跑测确认失败**

Run（在 `apps/web`）:

```bash
pnpm exec vitest run src/stock/overlayMath.test.ts
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `overlayMath.ts`**

```typescript
/**
 * 主图叠加用的交叉判定与交易日辅助。
 */
import type { OhlcvBar } from "./types";

/**
 * CROSS：A 上穿 B（前根 A≤B 且本根 A>B）。
 * @param a A 序列
 * @param b B 序列
 * @param i 当前下标
 */
export function crossUp(a: number[], b: number[], i: number): boolean {
  if (i < 1 || i >= a.length || i >= b.length) return false;
  return a[i - 1] <= b[i - 1] && a[i] > b[i];
}

/**
 * LONGCROSS：在 `i` 处，A 已上穿 B，且从交叉根起连续至少 `n` 根 A>B。
 * 通达信：`LONGCROSS(A,B,N)` 在满足「上穿后维持 N 根」的那根为真。
 * @param a A 序列
 * @param b B 序列
 * @param i 当前下标
 * @param n 维持根数
 */
export function longCrossUp(a: number[], b: number[], i: number, n: number): boolean {
  if (n < 1 || i < n || i >= a.length || i >= b.length) return false;
  const crossAt = i - n + 1;
  if (!crossUp(a, b, crossAt)) return false;
  for (let k = crossAt; k <= i; k += 1) {
    if (!(a[k] > b[k])) return false;
  }
  return true;
}

/**
 * 从 ISO ts 取北京日历日 YYYY-MM-DD。
 * @param ts ISO 时间
 */
export function beijingDateFromTs(ts: string): string | null {
  const ms = Date.parse(ts);
  if (Number.isNaN(ms)) return null;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(ms));
  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  if (!y || !m || !d) return null;
  return `${y}-${m}-${d}`;
}

/**
 * 过滤出北京日历日等于 `date` 的分钟线。
 * @param bars 分钟线
 * @param date YYYY-MM-DD
 */
export function filterBarsOnBeijingDate(bars: OhlcvBar[], date: string): OhlcvBar[] {
  return bars.filter((b) => b.ts != null && beijingDateFromTs(b.ts) === date);
}

/**
 * 自 `date` 回推 `n` 个交易日（跳过周六日；不处理法定假日）。
 * @param date YYYY-MM-DD
 * @param n 交易日数
 */
export function shiftTradingDaysBack(date: string, n: number): string {
  const [ys, ms, ds] = date.split("-").map(Number);
  const cursor = new Date(Date.UTC(ys, ms - 1, ds));
  let left = n;
  while (left > 0) {
    cursor.setUTCDate(cursor.getUTCDate() - 1);
    const dow = cursor.getUTCDay(); // 0=Sun … 与日历日对齐（UTC 存的是日历分量）
    if (dow !== 0 && dow !== 6) left -= 1;
  }
  const y = cursor.getUTCFullYear();
  const m = String(cursor.getUTCMonth() + 1).padStart(2, "0");
  const d = String(cursor.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
```

- [ ] **Step 4: 跑测确认通过**

```bash
pnpm exec vitest run src/stock/overlayMath.test.ts
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/stock/overlayMath.ts apps/web/src/stock/overlayMath.test.ts
git commit -m "feat(web): 主图叠加 CROSS/LONGCROSS 与交易日辅助"
```

---

### Task 2: 注册表扩展 + `buildIntradayDipOverlay`（TDD）

**Files:**
- Modify: `apps/web/src/stock/mainOverlays.ts`
- Modify: `apps/web/src/stock/mainOverlays.test.ts`

- [ ] **Step 1: 扩展类型与构建上下文（先改实现文件类型，再写测）**

在 `mainOverlays.ts` 增加：

```typescript
/** STICKLINE 竖条（low→high）。 */
export type MainOverlayStick = {
  time: Time;
  low: number;
  high: number;
  color: string;
};

/** 信号文字标记。 */
export type MainOverlayMarker = {
  time: Time;
  price: number;
  text: string;
  color: string;
};

/** 一族完整叠加产出。 */
export type MainOverlayBuildResult = {
  lines: MainOverlayLine[];
  sticks: MainOverlayStick[];
  markers: MainOverlayMarker[];
};

/** 构建上下文。 */
export type MainOverlayBuildContext = {
  /** 当天会话轴 ChartBar（图上已有） */
  chartBars: ChartBar[];
  /** 含预热的原始分钟线（按 ts）；分时指标用 */
  calcBars?: OhlcvBar[];
  /** 昨收 */
  preClose?: number | null;
  /** 当天 YYYY-MM-DD（北京） */
  sessionDate?: string;
};

export type MainOverlayDef = {
  id: string;
  label: string;
  periods: readonly ChartPeriod[];
  /** 兼容旧调用：仅线 */
  buildLines: (chartBars: ChartBar[]) => MainOverlayLine[];
  /** 完整产出；缺省则包一层 buildLines */
  build?: (ctx: MainOverlayBuildContext) => MainOverlayBuildResult;
};
```

增加辅助：

```typescript
/**
 * 统一调用 build / buildLines。
 * @param def 族定义
 * @param ctx 上下文
 */
export function buildMainOverlay(
  def: MainOverlayDef,
  ctx: MainOverlayBuildContext
): MainOverlayBuildResult {
  if (def.build) return def.build(ctx);
  return { lines: def.buildLines(ctx.chartBars), sticks: [], markers: [] };
}
```

- [ ] **Step 2: 更新/新增失败测试**

将 `shouldShowMainOverlaySelect` 期望改为 `intraday === true`。

将 `listOverlaysForPeriod("intraday")` 期望为 `["none", "intraday_dip"]`。

`MAIN_OVERLAYS` id 期望：`["sma", "ma_tactic", "none", "intraday_dip"]`。

新增：

```typescript
import { buildIntradayDipOverlay, buildMainOverlay, getMainOverlay } from "./mainOverlays";
import { toIntradayChartTime } from "./format";

describe("intraday registry", () => {
  it("lists none and intraday_dip", () => {
    expect(listOverlaysForPeriod("intraday").map((o) => o.id)).toEqual([
      "none",
      "intraday_dip",
    ]);
    expect(shouldShowMainOverlaySelect("intraday")).toBe(true);
  });
});

describe("buildIntradayDipOverlay", () => {
  it("computes support/resistance and strength stick colors", () => {
    // 构造两日分钟：昨日 40 根 close=10，今日 5 根递增；preClose=10
    const mk = (ts: string, close: number, high?: number, low?: number): OhlcvBar => ({
      ts,
      open: close,
      high: high ?? close,
      low: low ?? close,
      close,
      volume: 100,
    });
    const calc: OhlcvBar[] = [];
    for (let i = 0; i < 40; i += 1) {
      const mm = 31 + (i % 20);
      calc.push(mk(`2026-07-24T09:${String(mm).padStart(2, "0")}:00+08:00`, 10));
    }
    // 今日：抬高低点，便于验支撑阻力
    calc.push(mk("2026-07-27T09:31:00+08:00", 10, 12, 8));
    calc.push(mk("2026-07-27T09:32:00+08:00", 10.5, 12, 8));
    calc.push(mk("2026-07-27T09:33:00+08:00", 11, 12, 8));
    calc.push(mk("2026-07-27T09:34:00+08:00", 9, 12, 8));
    calc.push(mk("2026-07-27T09:35:00+08:00", 9.2, 12, 8));

    const dayBars = calc.filter((b) => b.ts!.startsWith("2026-07-27"));
    const chartBars = toChartBars(dayBars, "intraday");
    const result = buildIntradayDipOverlay({
      chartBars,
      calcBars: calc,
      preClose: 10,
      sessionDate: "2026-07-27",
    });

    expect(result.lines.map((l) => l.label).sort()).toEqual(
      ["MA30", "支撑", "强弱", "阻力"].sort()
    );
    // H1=max(10,12)=12, L1=min(10,8)=8, P1=4
    // 阻力=8+4*7/8=11.5, 支撑=8+4*0.5/8=8.25
    const resist = result.lines.find((l) => l.label === "阻力")!;
    const support = result.lines.find((l) => l.label === "支撑")!;
    expect(resist.points[resist.points.length - 1].value).toBeCloseTo(11.5, 8);
    expect(support.points[support.points.length - 1].value).toBeCloseTo(8.25, 8);
    expect(result.sticks.length).toBeGreaterThan(0);
  });

  it("none build returns empty", () => {
    const empty = buildMainOverlay(getMainOverlay("none"), {
      chartBars: [],
    });
    expect(empty).toEqual({ lines: [], sticks: [], markers: [] });
  });
});
```

- [ ] **Step 3: 跑测确认失败**

```bash
pnpm exec vitest run src/stock/mainOverlays.test.ts
```

Expected: FAIL（intraday 仍 false / 无 buildIntradayDipOverlay）

- [ ] **Step 4: 实现 `buildIntradayDipOverlay` 并注册**

要点（必须遵守）：

1. **禁止**对多日 `calcBars` 调用 `toChartBars(..., "intraday")` 做 EMA——会话轴会撞车。应按 `ts` 排序，用**顺序下标**或唯一 unix `time` 构造临时 `ChartBar[]` 调 `buildEmaSeries`。
2. 将 EMA 结果按 `beijingDateFromTs === sessionDate` 的 bar 映射到 `toIntradayChartTime(ts)`。
3. Running H1/L1：遍历当天 bars，`runHigh = max(preClose??-∞, highs…)`，`runLow = min(preClose??∞, lows…)`；每根更新后算阻力/支撑。
4. 强弱色带：每根当天 bar，`low=min(ma30,qiang), high=max(...)`，色 `#0000FF` / `#00FF00`。
5. `CROSS(支撑,现价)` → 黄 stick 支撑→阻力；`LONGCROSS(支撑,现价,2)` → marker `★B` at `支撑*1.001` 色 `#EAB308`；`LONGCROSS(现价,阻力,2)` → `★` 色 `#EF4444`。
6. **不**产出「现价」线。
7. `shouldShowMainOverlaySelect`：`day|week|month|intraday` 皆 true。
8. `getMainOverlay`：找不到时仍回退 `sma`（不要回退到 `none`）。

`none` 的 `build` / `buildLines` 返回空。

颜色常量：

```typescript
const DIP = {
  ma30: "#60a5fa",
  strength: "#a78bfa",
  bandUp: "#0000FF",
  bandDown: "#00FF00",
  level: "#00DD00",
  signalStick: "#EAB308",
  starB: "#EAB308",
  star: "#EF4444",
} as const;
```

- [ ] **Step 5: 跑测确认通过**

```bash
pnpm exec vitest run src/stock/mainOverlays.test.ts src/stock/overlayMath.test.ts
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/stock/mainOverlays.ts apps/web/src/stock/mainOverlays.test.ts
git commit -m "feat(web): 注册分时抄底主图指标并实现公式"
```

---

### Task 3: `StockChart` 分时叠加 sticks / lines / markers

**Files:**
- Modify: `apps/web/src/stock/StockChart.tsx`

- [ ] **Step 1: 扩展 props**

```typescript
type Props = {
  bars: OhlcvBar[];
  period: ChartPeriod;
  compact?: boolean;
  showVolume?: boolean;
  mainOverlayId?: string;
  /** 分时指标预热分钟线；缺省不用叠加计算 */
  overlayCalcBars?: OhlcvBar[];
  /** 昨收，支撑/阻力用 */
  preClose?: number | null;
  /** 当天北京日 YYYY-MM-DD */
  sessionDate?: string;
};
```

- [ ] **Step 2: 在 `period === "intraday"` 分支、均价线之后叠加**

```typescript
import { BarSeries, createSeriesMarkers, LineSeries, ... } from "lightweight-charts";
import { buildMainOverlay, getMainOverlay } from "./mainOverlays";

// 在均价 setData 之后：
const overlay = getMainOverlay(mainOverlayId);
const built = buildMainOverlay(overlay, {
  chartBars,
  calcBars: overlayCalcBars,
  preClose,
  sessionDate,
});

if (built.sticks.length > 0) {
  // 见下方「色带实现」：按颜色拆多个 BarSeries，勿用单一 up/down 系列
}
```

**色带实现（按此为准，避免 up/down 误色）：**

- 拆成两个 `BarSeries`：`bandUp`（蓝）只喂 `MA30>强弱` 的 stick；`bandDown`（绿）只喂反之。
- 黄信号 stick 用第三个 `BarSeries`（`#EAB308`）。
- 每个 stick：`open=low, close=high, high=high, low=low`（或反过来，只要竖直覆盖区间）。

然后画 `built.lines`（`LineSeries`，与日 K 相同选项）。

标记挂在主 `AreaSeries` 上：

```typescript
if (built.markers.length > 0) {
  createSeriesMarkers(
    series,
    built.markers.map((m) => ({
      time: m.time,
      position: "atPriceMiddle" as const,
      shape: "circle" as const,
      color: m.color,
      text: m.text,
      price: m.price,
      size: 0.5,
    }))
  );
}
```

依赖数组加入：`mainOverlayId`, `overlayCalcBars`, `preClose`, `sessionDate`。

- [ ] **Step 3: 手工/单测**

无新单测文件；跑现有：

```bash
pnpm exec vitest run src/stock/
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/stock/StockChart.tsx
git commit -m "feat(web): 分时图叠加 sticks/lines/markers"
```

---

### Task 4: `StockDetailView` 数据与下拉

**Files:**
- Modify: `apps/web/src/stock/StockDetailView.tsx`

- [ ] **Step 1: 状态默认改为 `none`**

```typescript
const [mainOverlayId, setMainOverlayId] = useState("none");
const [overlayCalcBars, setOverlayCalcBars] = useState<OhlcvBar[]>([]);
```

周期回退 effect 已存在：分时首项将是 `none`，日 K 首项 `sma`。

- [ ] **Step 2: 加载预热分钟线**

在 bars 加载成功且 `period === "intraday" && mainOverlayId === "intraday_dip"` 时请求：

```typescript
async function loadMinuteBarsRange(symbol: string, fromDate: string, toDate: string) {
  const params = new URLSearchParams({
    symbol,
    from: `${fromDate}T09:15:00+08:00`,
    to: `${toDate}T15:00:00+08:00`,
  });
  return api<OhlcvBar[]>(`/api/market/bars/minute?${params}`);
}

// fromDate = shiftTradingDaysBack(beijingToday(), 5)
```

`mainOverlayId !== "intraday_dip"` 时清空 `overlayCalcBars`。

- [ ] **Step 3: 传给 StockChart**

```tsx
<StockChart
  bars={bars.data ?? []}
  period={period}
  mainOverlayId={mainOverlayId}
  overlayCalcBars={period === "intraday" ? overlayCalcBars : undefined}
  preClose={quote.data?.pre_close}
  sessionDate={period === "intraday" ? beijingToday() : undefined}
  ...
/>
```

- [ ] **Step 4: 图例**

`overlayLegend`：对分时用 `buildMainOverlay` 的 `lines`（有 `calcBars` 时）；`none` 或空 lines 不展示。日 K 仍可用 `buildLines` 或统一 `buildMainOverlay`。

- [ ] **Step 5: 跑测**

```bash
pnpm exec vitest run src/stock/
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/stock/StockDetailView.tsx
git commit -m "feat(web): 分时指标下拉与 5 日预热分钟线"
```

---

### Task 5: 规格状态与收尾

**Files:**
- Modify: `docs/superpowers/specs/2026-08-01-intraday-main-overlay-design.md`（状态 → 已实现）
- Modify: `docs/superpowers/specs/2026-08-01-chart-main-overlay-design.md`（分时隐藏 → 分时亦显示，并指向新规格）

- [ ] **Step 1: 更新文档状态句**

旧规格中「`intraday` 隐藏」改为：「分时另见 `2026-08-01-intraday-main-overlay-design.md`」。

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-08-01-intraday-main-overlay-design.md docs/superpowers/specs/2026-08-01-chart-main-overlay-design.md
git commit -m "docs: 分时主图指标规格标为已实现"
```

---

## Spec coverage（自检）

| 规格项 | Task |
|--------|------|
| 分时下拉、默认无 | T4 |
| 分时抄底公式线/色带/标记 | T1–T2 |
| 不重画现价 / 保留均价 | T3（仅追加 series） |
| 5 日预热、图表当天 | T2 裁剪 + T4 请求 |
| DYNAINFO 昨收/高低 | T2 `preClose` + running |
| 日 K 行为不变 | T2 注册 periods 隔离 |
| 测试 CROSS/支撑阻力 | T1–T2 |

## Placeholder scan

无 TBD /「类似 Task N」占位。

## Type consistency

- `MainOverlayBuildResult` / `MainOverlayBuildContext` / `buildMainOverlay` 贯穿 T2–T4
- props：`overlayCalcBars`、`preClose`、`sessionDate` 在 T3 定义、T4 传入
