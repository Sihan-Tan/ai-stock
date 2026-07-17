# 分时开盘集合竞价 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分时图横轴前插 09:15–09:30，左侧竞价区浅底色 + 09:30 竖线；请求窗与 QMT 分钟（必要时 tick 聚合）覆盖该时段；顶栏均价/OHLC 仅统计连续竞价（≥09:30）。

**Architecture:** 前端会话坐标在 `format.ts` 统一前移 15 分钟；`StockDetailView` 将分钟请求 `from` 改为当日 09:15；`StockChart` 用时间坐标算 overlay 画竞价底色与竖线。后端 `get_minute_bars` 若 09:15–09:29 缺口，用 xtdata tick 聚合成 1m 补洞（无则空着，不报错）。

**Tech Stack:** React + `lightweight-charts`、Vitest、FastAPI 既有 `/bars/minute`、`desk_market.qmt_md`、pytest。

**Spec:** `docs/superpowers/specs/2026-07-18-intraday-auction-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `apps/web/src/stock/format.ts` | 会话序号含 09:15–09:30；刻度/摘要过滤；导出竞价常量 |
| `apps/web/src/stock/format.test.ts` | 坐标、刻度、摘要、toChartBars 断言更新 |
| `apps/web/src/stock/StockDetailView.tsx` | 分时 `from` → `09:15` |
| `apps/web/src/stock/StockChart.tsx` | 竞价区 overlay + 09:30 竖线；可见范围含竞价 |
| `packages/market/desk_market/qmt_md.py` | `get_minute_bars` 竞价缺口 tick→1m 补洞；Mock 可 seed |
| `tests/test_qmt_md_auction_minute.py` | Mock：分钟缺竞价时 tick 聚合补齐 |

**不做：** 收盘竞价分区、双图并排、改日/周/月 K。

---

### Task 1: 会话坐标前插 09:15–09:30（纯前端）

**Files:**
- Modify: `apps/web/src/stock/format.ts`
- Modify: `apps/web/src/stock/format.test.ts`

- [ ] **Step 1: 改写失败测试（旧 09:30→0 预期作废）**

将 `format.test.ts` 中 `ashare session axis` 与 `toChartBars` 分时断言改为：

```ts
describe("ashare session axis", () => {
  it("maps auction and continuous session onto continuous indexes", () => {
    expect(toAshareSessionIndex(9, 15)).toBe(0);
    expect(toAshareSessionIndex(9, 25)).toBe(10);
    expect(toAshareSessionIndex(9, 29)).toBe(14);
    expect(toAshareSessionIndex(9, 30)).toBe(15);
    expect(toAshareSessionIndex(11, 30)).toBe(135);
    expect(toAshareSessionIndex(13, 0)).toBe(135);
    expect(toAshareSessionIndex(15, 0)).toBe(255);
    expect(toAshareSessionIndex(12, 0)).toBeNull();
    expect(toAshareSessionIndex(9, 14)).toBeNull();
  });

  it("formats key session labels", () => {
    expect(formatAshareSessionLabel(0)).toBe("09:15");
    expect(formatAshareSessionLabel(15)).toBe("09:30");
    expect(formatAshareSessionLabel(135)).toBe("11:30/13:00");
    expect(formatAshareSessionLabel(255)).toBe("15:00");
  });

  it("formats intraday crosshair as HH:mm", () => {
    expect(formatIntradayCrosshairTime(1_000_000 as never)).toBe("09:15");
    expect(formatIntradayCrosshairTime(1_000_015 as never)).toBe("09:30");
    expect(formatIntradayCrosshairTime(1_000_046 as never)).toBe("10:01");
    expect(formatIntradayCrosshairTime(1_000_135 as never)).toBe("11:30/13:00");
  });
});
```

`toChartBars` 分时用例：09:30 的 `time` 改为 `1_000_015`；11:30/13:00 改为 `1_000_135`；并新增一根 `09:15`（`2026-07-15T01:15:00.000Z`）期望 `time: 1_000_000`。

- [ ] **Step 2: 跑测确认失败**

Run: `cd apps/web && npx vitest run src/stock/format.test.ts`

Expected: FAIL（旧坐标仍为 09:30→0）

- [ ] **Step 3: 实现坐标与刻度**

在 `format.ts` 中：

```ts
/** 开盘集合竞价+空档跨度（09:15→09:30 = 15 分钟）。 */
export const ASHARE_AUCTION_SPAN = 15;
/** 上午连续竞价跨度（09:30→11:30 = 120）。 */
const AM_SPAN = 11 * 60 + 30 - (9 * 60 + 30);
/** 连续竞价全天分钟数（含午休共点）：0…240，再叠加竞价前缀。 */
const CONTINUOUS_LAST_INDEX = AM_SPAN + (15 * 60 - 13 * 60); // 240
/** 含竞价前缀的会话最后序号：09:15→0 … 15:00→255。 */
export const ASHARE_SESSION_LAST_INDEX = ASHARE_AUCTION_SPAN + CONTINUOUS_LAST_INDEX; // 255
/** 连续竞价起点序号（=09:30）。 */
export const ASHARE_CONTINUOUS_START_INDEX = ASHARE_AUCTION_SPAN; // 15
```

重写 `toAshareSessionIndex`：

```ts
export function toAshareSessionIndex(hour: number, minute: number): number | null {
  const mins = hour * 60 + minute;
  const auctionStart = 9 * 60 + 15;
  const amStart = 9 * 60 + 30;
  const amEnd = 11 * 60 + 30;
  const pmStart = 13 * 60;
  const pmEnd = 15 * 60;

  if (mins >= auctionStart && mins < amStart) {
    return mins - auctionStart;
  }
  if (mins >= amStart && mins <= amEnd) {
    return ASHARE_AUCTION_SPAN + (mins - amStart);
  }
  if (mins >= pmStart && mins <= pmEnd) {
    return ASHARE_AUCTION_SPAN + AM_SPAN + (mins - pmStart);
  }
  return null;
}
```

重写 `formatAshareSessionLabel` / `formatIntradayTickMark`：关键点为 `0→09:15`、`ASHARE_CONTINUOUS_START_INDEX→09:30`、`ASHARE_AUCTION_SPAN+AM_SPAN→11:30/13:00`、`ASHARE_SESSION_LAST_INDEX→15:00`；其余由序号反算墙钟（竞价段用 `9:15+idx`，上午用 `9:30+(idx-15)`，下午用 `13:00+(idx-135)`）。

- [ ] **Step 4: 跑测通过**

Run: `cd apps/web && npx vitest run src/stock/format.test.ts`

Expected: PASS（本 Task 相关用例；若摘要用例尚未改，先别改摘要，或本步只跑 session 相关 describe）

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/stock/format.ts apps/web/src/stock/format.test.ts
git commit -m "feat(web): extend intraday axis for 09:15 auction window"
```

---

### Task 2: 顶栏摘要与均价线排除竞价段

**Files:**
- Modify: `apps/web/src/stock/format.ts`（`summarizeIntradayBars`、`buildIntradayAvgSeries`）
- Modify: `apps/web/src/stock/format.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
it("ignores auction bars before 09:30 for OHLC and VWAP", () => {
  expect(
    summarizeIntradayBars([
      {
        ts: "2026-07-15T01:20:00.000Z", // 09:20 竞价
        open: 9,
        high: 12,
        low: 8,
        close: 11,
        volume: 1000,
        amount: 11000,
      },
      {
        ts: "2026-07-15T01:30:00.000Z", // 09:30
        open: 10,
        high: 10.3,
        low: 9.9,
        close: 10.2,
        volume: 100,
        amount: 1020,
      },
      {
        ts: "2026-07-15T01:31:00.000Z",
        open: 10.2,
        high: 10.5,
        low: 10.1,
        close: 10.4,
        volume: 100,
        amount: 1040,
      },
    ])
  ).toEqual({
    avg: 10.3,
    open: 10,
    close: 10.4,
    high: 10.5,
    low: 9.9,
  });
});
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd apps/web && npx vitest run src/stock/format.test.ts -t "ignores auction"`

Expected: FAIL（当前会把竞价 high=12 算进去）

- [ ] **Step 3: 实现过滤**

在 `format.ts` 增加：

```ts
/**
 * 是否属于连续竞价段（≥09:30）。
 * @param value ISO 时间
 */
export function isContinuousSessionTs(value: string | undefined): boolean {
  if (!value) return false;
  const hm = getBeijingHourMinute(value);
  if (!hm) return false;
  const index = toAshareSessionIndex(hm.hour, hm.minute);
  return index != null && index >= ASHARE_CONTINUOUS_START_INDEX;
}
```

`summarizeIntradayBars`：先 `sorted.filter(b => isContinuousSessionTs(b.ts))`，空则返回全 null。

`buildIntradayAvgSeries`：仅对 `isContinuousSessionTs` 为真的 bar 累加 VWAP（图表黄线与顶栏一致）。价格主线 / 成交量仍含竞价（`toChartBars` 不过滤）。

- [ ] **Step 4: 跑全文件测试**

Run: `cd apps/web && npx vitest run src/stock/format.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/stock/format.ts apps/web/src/stock/format.test.ts
git commit -m "feat(web): exclude auction from intraday VWAP summary"
```

---

### Task 3: 分时请求窗改为 09:15

**Files:**
- Modify: `apps/web/src/stock/StockDetailView.tsx`（`loadBars`）

- [ ] **Step 1: 修改 from**

```ts
from: `${date}T09:15:00+08:00`,
```

`to` 仍为 `15:00`。无需新测（纯常量）；若有 e2e/契约测到 09:30 则同步改。

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/stock/StockDetailView.tsx
git commit -m "feat(web): request intraday bars from 09:15"
```

---

### Task 4: 竞价区浅底色 + 09:30 竖线

**Files:**
- Modify: `apps/web/src/stock/StockChart.tsx`

- [ ] **Step 1: 增加 overlay 状态与绘制**

在分时分支、`setVisibleRange` 之后：

1. 从 `format` 再导入 `ASHARE_CONTINUOUS_START_INDEX`、`ASHARE_AUCTION_SPAN`（若需要）。
2. 用绝对定位 div 盖在图表容器上（`pointer-events-none`），根据 `chart.timeScale().timeToCoordinate` 计算：
   - 竞价底色：`left = timeToCoordinate(BASE+0)`，`width = timeToCoordinate(BASE+15) - left`
   - 竖线：`left = timeToCoordinate(BASE+15)`，宽 1px
3. 在 `subscribeVisibleTimeRangeChange` / `ResizeObserver` 里重算坐标；卸载时取消订阅。
4. 底色建议 `rgba(148, 163, 184, 0.12)`；竖线 `rgba(148, 163, 184, 0.55)`。高度覆盖主图区域即可（可用容器 100%）。

示意结构：

```tsx
const [auctionBand, setAuctionBand] = useState<{ left: number; width: number; lineLeft: number } | null>(null);

// 在 createChart 后：
const syncAuctionOverlay = () => {
  const ts = chart.timeScale();
  const x0 = ts.timeToCoordinate((INTRADAY_TIME_BASE + 0) as UTCTimestamp);
  const x1 = ts.timeToCoordinate((INTRADAY_TIME_BASE + ASHARE_CONTINUOUS_START_INDEX) as UTCTimestamp);
  if (x0 == null || x1 == null) {
    setAuctionBand(null);
    return;
  }
  setAuctionBand({ left: x0, width: Math.max(0, x1 - x0), lineLeft: x1 });
};
syncAuctionOverlay();
chart.timeScale().subscribeVisibleLogicalRangeChange(syncAuctionOverlay);
```

JSX（容器相对定位）：

```tsx
<div ref={containerRef} className="relative w-full" style={{ height: chartHeight }}>
  {period === "intraday" && auctionBand ? (
    <>
      <div
        className="pointer-events-none absolute top-0 bottom-0 z-0"
        style={{ left: auctionBand.left, width: auctionBand.width, background: "rgba(148, 163, 184, 0.12)" }}
      />
      <div
        className="pointer-events-none absolute top-0 bottom-0 z-0 w-px"
        style={{ left: auctionBand.lineLeft, background: "rgba(148, 163, 184, 0.55)" }}
      />
    </>
  ) : null}
</div>
```

注意：lightweight-charts canvas 可能盖住 div——若 z-index 无效，改为在 chart 容器**外层**包一层 `relative`，overlay 与 chart 同级且 chart 容器 `z-10` 不行时，用 **chart 上方兄弟节点** 且保证 chart 背景 transparent（已是），或把 overlay 放在 chart 内部第一个子节点并用 `z-index` + 不挡事件。验收时以肉眼可见为准；若被 canvas 挡住，改用 `chart.panes()` 自定义 primitive 或在主图下方用极矮 Histogram 占位——优先 overlay。

- [ ] **Step 2: 手动点检**（实现者本地开详情分时）

Expected：左侧一段浅底、09:30 竖线；刻度含 09:15 / 09:30。

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/stock/StockChart.tsx
git commit -m "feat(web): shade auction zone on intraday chart"
```

---

### Task 5: QMT 分钟竞价缺口用 tick 聚合补齐

**Files:**
- Modify: `packages/market/desk_market/qmt_md.py`（`MockQmtMarketData` + `XtdataMarketData`）
- Create: `tests/test_qmt_md_auction_minute.py`

- [ ] **Step 1: 写失败测试（Mock）**

```python
"""竞价分钟缺口：tick 聚合补 09:15–09:29。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from desk_market.qmt_md import MockQmtMarketData


def test_get_minute_bars_fills_auction_from_ticks():
    md = MockQmtMarketData()
    md.seed_minute(
        "600519.SH",
        [
            {
                "ts": datetime(2026, 7, 15, 9, 30, 0),
                "open": 10,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 100,
                "amount": 1010,
            }
        ],
    )
    md.seed_ticks(
        "600519.SH",
        [
            {"ts": datetime(2026, 7, 15, 9, 15, 10), "last": 9.8, "volume": 10, "amount": 98},
            {"ts": datetime(2026, 7, 15, 9, 15, 40), "last": 9.9, "volume": 20, "amount": 198},
            {"ts": datetime(2026, 7, 15, 9, 20, 5), "last": 10.0, "volume": 5, "amount": 50},
        ],
    )
    df = md.get_minute_bars("600519.SH", "2026-07-15 09:15:00", "2026-07-15 09:35:00")
    assert not df.empty
    minutes = {pd.Timestamp(ts).strftime("%H:%M") for ts in df["ts"]}
    assert "09:15" in minutes
    assert "09:20" in minutes
    assert "09:30" in minutes
    row_915 = df[df["ts"].map(lambda t: pd.Timestamp(t).hour == 9 and pd.Timestamp(t).minute == 15)].iloc[0]
    assert float(row_915["open"]) == 9.8
    assert float(row_915["close"]) == 9.9
    assert float(row_915["high"]) == 9.9
    assert float(row_915["low"]) == 9.8
```

若现有 `seed_minute` 签名不同，按 `MockQmtMarketData` 实际 API 调整；缺少 `seed_ticks` 则本 Task 一并添加。

- [ ] **Step 2: 跑测确认失败**

Run: `python -m pytest tests/test_qmt_md_auction_minute.py -v`

Expected: FAIL（无 `seed_ticks` 或未补竞价）

- [ ] **Step 3: Mock 实现**

- `MockQmtMarketData`：`_ticks: dict[str, list]` + `seed_ticks(symbol, rows)`。
- 在 `get_minute_bars` 末尾调用共享逻辑 `_fill_auction_minutes(df, ticks, start, end)`：
  - 目标分钟：墙钟 `09:15`…`09:29`（整分桶；tick 的分钟用 `floor`）。
  - 若该分钟已在 `df` 中则跳过。
  - 否则对该分钟 ticks：`open=first.last`，`high=max`，`low=min`，`close=last.last`，`volume=sum`，`amount=sum`，`ts=当日该分钟 :00`。
  - 合并后按 `ts` 排序。

- [ ] **Step 4: Xtdata 实现**

在 `XtdataMarketData.get_minute_bars` 取得 `1m` 的 `out` 后：

```python
out = self._ensure_auction_minutes(symbol, out, start_ts, end_ts)
```

`_ensure_auction_minutes`：

1. 若 `start_ts.time() >= 09:30` 或不需要竞价窗，直接返回。
2. 检查是否已有任一 `09:15<=ts<09:30` 的行；若已有足够（≥1）可仍尝试补缺分钟。
3. 对缺失的竞价分钟：`download_history_data(..., period="tick", start_time=当日091500, end_time=当日092959)`，再 `get_market_data_ex(..., period="tick", ...)`。
4. 将 tick 的时间与 `lastPrice`/`volume`/`amount`（字段名兼容大小写）聚合成分钟行，`concat` 进 `out`。
5. 任意异常：记 `logger.warning`，返回原 `out`（不抛）。

空档无 tick：**不插假量**。

- [ ] **Step 5: 跑测通过**

Run: `python -m pytest tests/test_qmt_md_auction_minute.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packages/market/desk_market/qmt_md.py tests/test_qmt_md_auction_minute.py
git commit -m "feat(market): fill opening auction minutes from QMT ticks"
```

---

### Task 6: 回归与验收

**Files:** 无新文件（或按失败补测）

- [ ] **Step 1: 前端单测**

Run: `cd apps/web && npx vitest run src/stock/format.test.ts`

Expected: PASS

- [ ] **Step 2: 后端相关测**

Run: `python -m pytest tests/test_qmt_md_auction_minute.py tests/test_market_pipeline_qmt_md.py -q`

Expected: PASS

- [ ] **Step 3: 手工验收清单**

1. 详情页分时：轴上有 **09:15**、**09:30**；左侧浅底 + 竖线。
2. 有 QMT 竞价数据时，09:15–09:30 有价/量。
3. 顶栏均价/OHLC 不受竞价极端价影响（对比仅看 ≥09:30）。
4. 无竞价数据时连续竞价段仍正常。

- [ ] **Step 4: 若手工改动有修正则再 commit**

```bash
git add -u
git commit -m "fix: polish intraday auction chart edge cases"
```

（无改动则跳过）

---

## Spec coverage

| Spec 项 | Task |
|---------|------|
| 时段 09:15–09:30 | 1, 3, 5 |
| 同轴 + 底色 + 09:30 竖线 | 1, 4 |
| 价/量含竞价 | 1（坐标不丢）、3、5 |
| 摘要仅 ≥09:30 | 2 |
| QMT 1m + tick 补洞 | 5 |
| 无数据不炸 | 5 异常吞掉 + 4 空态 |
| 不做收盘竞价 | 未列入 |

## 自我审查

- 无 TBD/占位步骤。
- 序号常量：`0/15/135/255` 与 `ASHARE_AUCTION_SPAN=15` 前后一致。
- `buildIntradayAvgSeries` 与顶栏摘要均排除竞价，避免双口径。
