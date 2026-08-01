# 标的图主图指标下拉 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在日/周/月 K 工具条增加主图指标族下拉；首版仅「移动均线」（MA5–MA60），用注册表便于后续加「均线战法」。

**Architecture:** 新增 `mainOverlays.ts` 注册表（`sma` → `buildLines`）。`StockDetailView` 在周期按钮组内用竖线 + `<select>`（布局 C）；`StockChart` 按当前族叠加主图线，不再写死 `period === "day"`。分时隐藏下拉。

**Tech Stack:** React 19、TypeScript、Vitest、lightweight-charts、现有 `buildSmaSeries` / `DAILY_MA_LINES`。

**Spec:** `docs/superpowers/specs/2026-08-01-chart-main-overlay-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `apps/web/src/stock/mainOverlays.ts` | 注册表、列表过滤、可见性辅助 |
| `apps/web/src/stock/mainOverlays.test.ts` | 单测 |
| `apps/web/src/stock/StockChart.tsx` | 按 `mainOverlayId` 画主图叠加 |
| `apps/web/src/stock/StockDetailView.tsx` | 工具条下拉、状态、图例随族/周期 |

---

### Task 1: `mainOverlays` 注册表（TDD）

**Files:**
- Create: `apps/web/src/stock/mainOverlays.ts`
- Create: `apps/web/src/stock/mainOverlays.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest";
import {
  MAIN_OVERLAYS,
  listOverlaysForPeriod,
  shouldShowMainOverlaySelect,
  buildSmaOverlayLines,
} from "./mainOverlays";
import { buildSmaSeries, DAILY_MA_LINES, toChartBars } from "./format";
import type { OhlcvBar } from "./types";

describe("shouldShowMainOverlaySelect", () => {
  it("shows for day/week/month only", () => {
    expect(shouldShowMainOverlaySelect("day")).toBe(true);
    expect(shouldShowMainOverlaySelect("week")).toBe(true);
    expect(shouldShowMainOverlaySelect("month")).toBe(true);
    expect(shouldShowMainOverlaySelect("intraday")).toBe(false);
  });
});

describe("listOverlaysForPeriod", () => {
  it("lists sma for day and empty for intraday", () => {
    const day = listOverlaysForPeriod("day");
    expect(day.map((o) => o.id)).toEqual(["sma"]);
    expect(day[0].label).toBe("移动均线");
    expect(listOverlaysForPeriod("intraday")).toEqual([]);
  });

  it("registry has only sma in v1", () => {
    expect(MAIN_OVERLAYS.map((o) => o.id)).toEqual(["sma"]);
  });
});

describe("buildSmaOverlayLines", () => {
  it("matches buildSmaSeries for each window", () => {
    const raw: OhlcvBar[] = Array.from({ length: 10 }, (_, i) => ({
      date: `2026-01-${String(i + 1).padStart(2, "0")}`,
      open: 10,
      high: 11,
      low: 9,
      close: 10 + i,
      volume: 1,
    }));
    const chartBars = toChartBars(raw, "day");
    const lines = buildSmaOverlayLines(chartBars);
    expect(lines).toHaveLength(DAILY_MA_LINES.length);
    for (let i = 0; i < DAILY_MA_LINES.length; i += 1) {
      const expectPts = buildSmaSeries(chartBars, DAILY_MA_LINES[i].window);
      expect(lines[i].label).toBe(DAILY_MA_LINES[i].label);
      expect(lines[i].color).toBe(DAILY_MA_LINES[i].color);
      expect(lines[i].points).toEqual(expectPts);
    }
  });
});
```

- [ ] **Step 2: 跑测确认失败**

Run（在 `apps/web`）:

```bash
pnpm exec vitest run src/stock/mainOverlays.test.ts
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `mainOverlays.ts`**

```typescript
/**
 * 主图叠加指标族注册表（首版仅移动均线）。
 */
import type { Time } from "lightweight-charts";
import { buildSmaSeries, DAILY_MA_LINES, type ChartBar } from "./format";
import type { ChartPeriod } from "./types";

/** 一条主图叠加线。 */
export type MainOverlayLine = {
  label: string;
  color: string;
  points: Array<{ time: Time; value: number }>;
};

/** 主图指标族。 */
export type MainOverlayDef = {
  id: string;
  label: string;
  periods: readonly ChartPeriod[];
  buildLines: (chartBars: ChartBar[]) => MainOverlayLine[];
};

/** 日/周/月可见。 */
const KLINE_PERIODS = ["day", "week", "month"] as const;

/**
 * 是否显示主图指标下拉。
 * @param period 当前周期
 */
export function shouldShowMainOverlaySelect(period: ChartPeriod): boolean {
  return (KLINE_PERIODS as readonly string[]).includes(period);
}

/**
 * 用现有 MA 配置生成叠加线。
 * @param chartBars 已转换的 K 线
 */
export function buildSmaOverlayLines(chartBars: ChartBar[]): MainOverlayLine[] {
  return DAILY_MA_LINES.map((ma) => ({
    label: ma.label,
    color: ma.color,
    points: buildSmaSeries(chartBars, ma.window),
  }));
}

/** 全部主图族（首版仅 sma）。 */
export const MAIN_OVERLAYS: readonly MainOverlayDef[] = [
  {
    id: "sma",
    label: "移动均线",
    periods: KLINE_PERIODS,
    buildLines: buildSmaOverlayLines,
  },
] as const;

/**
 * 某周期可选的主图族。
 * @param period 当前周期
 */
export function listOverlaysForPeriod(period: ChartPeriod): MainOverlayDef[] {
  return MAIN_OVERLAYS.filter((o) => o.periods.includes(period));
}

/**
 * 按 id 取定义；找不到则回退 sma。
 * @param id 族 id
 */
export function getMainOverlay(id: string): MainOverlayDef {
  return MAIN_OVERLAYS.find((o) => o.id === id) ?? MAIN_OVERLAYS[0];
}
```

- [ ] **Step 4: 跑测通过**

```bash
pnpm exec vitest run src/stock/mainOverlays.test.ts
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/stock/mainOverlays.ts apps/web/src/stock/mainOverlays.test.ts
git commit -m "feat(web): 主图指标族注册表（移动均线）"
```

---

### Task 2: StockChart 按族叠加

**Files:**
- Modify: `apps/web/src/stock/StockChart.tsx`

- [ ] **Step 1: 扩展 props**

```typescript
export type StockChartProps = {
  period: ChartPeriod;
  bars: OhlcvBar[];
  compact?: boolean;
  /** 主图指标族；分时可忽略。默认 sma */
  mainOverlayId?: string;
};
```

- [ ] **Step 2: 替换写死的 day-only MA**

在 `StockChart` 函数签名加入 `mainOverlayId = "sma"`。

把：

```typescript
      if (period === "day") {
        for (const ma of DAILY_MA_LINES) {
          const points = buildSmaSeries(chartBars, ma.window);
          ...
        }
      }
```

改为：

```typescript
      if (period === "day" || period === "week" || period === "month") {
        const { getMainOverlay } = await import("./mainOverlays"); // 勿用动态 import
```

**正确写法（静态 import）：** 文件顶部：

```typescript
import { getMainOverlay } from "./mainOverlays";
```

绘制：

```typescript
      if (period === "day" || period === "week" || period === "month") {
        const overlay = getMainOverlay(mainOverlayId);
        for (const line of overlay.buildLines(chartBars)) {
          if (line.points.length === 0) continue;
          const maSeries = chart.addSeries(LineSeries, {
            color: line.color,
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          maSeries.setData(line.points);
        }
      }
```

- [ ] **Step 3: 把 `mainOverlayId` 加入 useEffect 依赖数组**（原依赖含 `period` / `chartBars` 等处一并加上）。

可移除仅用于 MA 的 `DAILY_MA_LINES` / `buildSmaSeries` 直接 import（若文件内不再使用）。

- [ ] **Step 4: 跑相关前端测试**

```bash
pnpm exec vitest run src/stock/
```

Expected: PASS（含 mainOverlays + format）

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/stock/StockChart.tsx
git commit -m "feat(web): StockChart 按主图指标族叠加均线"
```

---

### Task 3: StockDetailView 工具条 + 图例

**Files:**
- Modify: `apps/web/src/stock/StockDetailView.tsx`

- [ ] **Step 1: 状态与选项**

在组件内：

```typescript
import {
  getMainOverlay,
  listOverlaysForPeriod,
  shouldShowMainOverlaySelect,
} from "./mainOverlays";

const [mainOverlayId, setMainOverlayId] = useState("sma");
```

- [ ] **Step 2: 工具条布局 C**

将周期按钮容器改为：同一 `inline-flex` 条内：`PERIODS` 按钮 → 若 `shouldShowMainOverlaySelect(period)` 则竖线 + `<select>`。

示意结构（样式对齐现有按钮条）：

```tsx
<div className="inline-flex items-center rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-1">
  {PERIODS.map((item) => (
    <button ...>{item.label}</button>
  ))}
  {shouldShowMainOverlaySelect(period) && (
    <>
      <span
        className="mx-1 h-5 w-px shrink-0 bg-[var(--desk-line)]"
        aria-hidden
      />
      <select
        className="rounded-md bg-transparent px-2 py-1.5 text-sm text-[var(--desk-text)] outline-none"
        value={mainOverlayId}
        aria-label="主图指标"
        onChange={(e) => setMainOverlayId(e.target.value)}
      >
        {listOverlaysForPeriod(period).map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </>
  )}
</div>
```

注意：`<option>` 在深色主题下依赖系统原生样式即可；不要在首版引入「均线战法」。

- [ ] **Step 3: 传给 StockChart**

```tsx
<StockChart
  period={period}
  bars={bars.data ?? []}
  compact={compact}
  mainOverlayId={mainOverlayId}
/>
```

- [ ] **Step 4: 图例随日/周/月 + 当前族**

把原 `dailyMaPrices`（仅 `period === "day"`）改为：

```typescript
  const overlayLegend = useMemo(() => {
    if (!shouldShowMainOverlaySelect(period) || !bars.data?.length) return [];
    const chartBars = toChartBars(bars.data, period);
    const overlay = getMainOverlay(mainOverlayId);
    return overlay.buildLines(chartBars).map((line) => ({
      label: line.label,
      color: line.color,
      value: line.points.length ? line.points[line.points.length - 1].value : null,
    }));
  }, [bars.data, period, mainOverlayId]);
```

模板里原 `dailyMaPrices.map` 改为 `overlayLegend.map`（变量名同步）。

若 `mainOverlayId` 不在当前 `listOverlaysForPeriod(period)` 中（未来扩展时），在 `useEffect` 或渲染前钳制为列表第一项：

```typescript
useEffect(() => {
  const opts = listOverlaysForPeriod(period);
  if (opts.length && !opts.some((o) => o.id === mainOverlayId)) {
    setMainOverlayId(opts[0].id);
  }
}, [period, mainOverlayId]);
```

- [ ] **Step 5: 手工核对清单（实现者自检）**

- 日 K：下拉默认「移动均线」，MA 与改前一致  
- 周 K：有下拉与均线  
- 分时：无下拉  
- 选项中无「均线战法」

- [ ] **Step 6: 跑测并提交**

```bash
pnpm exec vitest run src/stock/
```

```bash
git add apps/web/src/stock/StockDetailView.tsx
git commit -m "feat(web): K 线工具条主图指标下拉（移动均线）"
```

---

### Task 4: 文档收尾

**Files:**
- Modify: `docs/superpowers/specs/2026-08-01-chart-main-overlay-design.md`（状态 → 已实现）

- [ ] **Step 1: 全量相关测试**

```bash
cd apps/web && pnpm exec vitest run src/stock/
```

Expected: PASS

- [ ] **Step 2: 规格状态改为「已实现」并 commit**

```bash
git add docs/superpowers/specs/2026-08-01-chart-main-overlay-design.md
git commit -m "docs: 主图指标下拉规格标为已实现"
```

---

## Self-Review (plan vs spec)

| Spec | Task |
|------|------|
| 布局 C 同条工具条 | 3 |
| 仅 day/week/month | 1, 3 |
| 注册表 + sma | 1 |
| 周/月也画 SMA | 2, 3 图例 |
| 无均线战法 | 1 注册表仅 sma |
| 测试 | 1, 4 |

无 TBD；`getMainOverlay` / `listOverlaysForPeriod` / `shouldShowMainOverlaySelect` 命名前后一致。
