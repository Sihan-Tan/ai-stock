# 分时可配置槽宽轮询 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分时槽宽 = 设置项 `intraday_poll_interval_sec`（默认 10，5–60）；分钟线铺底 + 报价按槽补点；主图与副图共用槽序列。

**Architecture:** 后端 settings 持久化间隔；前端 `format`/`intradaySlots` 提供槽索引与占位；`buildIntradaySlotSeries` 合并分钟线与 live 报价；`StockDetailView` 双定时（报价=S、分钟≈30–60s）；`StockChart` 按 `slotSec` 设可见范围与刻度。

**Tech Stack:** Python settings_store、FastAPI、React、Vitest、lightweight-charts、现有 quote/minute API。

**Spec:** `docs/superpowers/specs/2026-08-01-intraday-slot-poll-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `packages/common/desk_common/settings.py` | 字段默认 10 |
| `packages/common/desk_common/settings_store.py` | env 映射、public、patch clamp |
| `apps/api/app/routes/settings.py` | SettingsPatch |
| `apps/web/src/pages/Settings.tsx` | UI 输入 |
| `apps/web/src/stock/intradaySlots.ts` | 槽数学、占位、分钟→槽、现价→槽 |
| `apps/web/src/stock/intradaySlots.test.ts` | 单测 |
| `apps/web/src/stock/format.ts` | 刻度格式兼容 slot（或委托 slots） |
| `apps/web/src/stock/StockDetailView.tsx` | 读设置、双轮询、组序列 |
| `apps/web/src/stock/StockChart.tsx` | `slotSec` 轴与副图输入 |

---

### Task 1: 设置项后端（TDD 若有现成 settings 测则跟上）

**Files:**
- Modify: `packages/common/desk_common/settings.py`
- Modify: `packages/common/desk_common/settings_store.py`
- Modify: `apps/api/app/routes/settings.py`
- Create or extend: `tests/` 下 settings 相关测（若仓库已有 `test_settings*` 则扩展；否则加 `tests/test_intraday_poll_interval.py`）

- [ ] **Step 1: 加字段**

```python
# settings.py
intraday_poll_interval_sec: int = 10
"""分时槽宽兼报价轮询间隔（秒，5–60）。"""
```

```python
# settings_store FIELD_TO_ENV
"intraday_poll_interval_sec": "INTRADAY_POLL_INTERVAL_SEC",
```

`public_settings` 返回该字段；`apply_settings_patch`：

```python
elif field == "intraday_poll_interval_sec":
    v = int(value)
    v = max(5, min(60, v))
    updates[field] = v
```

`SettingsPatch` 增加 `intraday_poll_interval_sec: int | None = None`。

- [ ] **Step 2: 测试 clamp**

```python
def test_intraday_poll_interval_clamped(tmp_path, monkeypatch):
    # patch 到临时 .env 或 mock apply；断言 3→5，100→60，10→10
```

按仓库现有 settings 测试风格编写（先 `rg apply_settings_patch`）。

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(settings): 分时刷新间隔 intraday_poll_interval_sec"
```

---

### Task 2: Settings 前端

**Files:**
- Modify: `apps/web/src/pages/Settings.tsx`

- [ ] **Step 1:** `AppSettings` / 默认 form 增加 `intraday_poll_interval_sec?: number`（默认 10）。
- [ ] **Step 2:** 保存 payload 带上该字段；输入控件放在与行情/展示相近分组，label「分时刷新间隔（秒）」，`min=5 max=60`。
- [ ] **Step 3:** Commit `feat(web): 设置页分时刷新间隔`

---

### Task 3: 槽数学 `intradaySlots.ts`（TDD）

**Files:**
- Create: `apps/web/src/stock/intradaySlots.ts`
- Create: `apps/web/src/stock/intradaySlots.test.ts`

导出常量与函数（秒级会话总长：现网分钟轴最后 index 255 → 会话跨度按**秒**用同一拍卖+连续逻辑）：

```typescript
/** 校验并钳制间隔。 */
export function clampIntradayPollIntervalSec(raw: unknown): number {
  const n = Math.round(Number(raw));
  if (!Number.isFinite(n)) return 10;
  return Math.min(60, Math.max(5, n));
}

/**
 * 将北京时分秒映射到槽序号（slotSec 为槽宽）。
 * @returns null 若非交易时段
 */
export function toAshareSessionSlot(
  hour: number,
  minute: number,
  second: number,
  slotSec: number
): number | null;

/** 全天槽数最后下标（含）。 */
export function ashareSessionLastSlot(slotSec: number): number;

/** 连续竞价起点槽（09:30:00）。 */
export function ashareContinuousStartSlot(slotSec: number): number;

export function buildIntradaySlotPlaceholders(slotSec: number): Array<{ time: UTCTimestamp }>;

/**
 * 分钟 OHLCV → 槽序列 ChartBar（落到分钟起点槽；同槽后写覆盖）。
 */
export function mapMinuteBarsToSlots(bars: OhlcvBar[], slotSec: number): ChartBar[];

/**
 * 在槽序列上写入/更新某一槽的 close/value（报价补点）。
 */
export function upsertSlotPrice(
  slots: ChartBar[],
  slotIndex: number,
  price: number
): ChartBar[];
```

实现要点：

- 先算「会话内秒序号」`sessionSecond`（与 `toAshareSessionIndex` 同边界，再 `*60 + second`；11:30 与 13:00 共点规则保持：13:00 秒序接在 11:30）。
- `slotIndex = floor(sessionSecond / slotSec)`。
- `lastSlot = floor(sessionLastSecond / slotSec)`。
- 伪时间：`1_000_000 + slotIndex`（导出 `INTRADAY_TIME_BASE` 或从 format 复用）。

测试：

```typescript
expect(clampIntradayPollIntervalSec(3)).toBe(5);
expect(clampIntradayPollIntervalSec(100)).toBe(60);
// S=10: 09:30:00 与 09:30:09 同槽；09:30:10 下一槽
// S=60: lastSlot === 255（与旧分钟轴一致）
```

- [ ] Commit: `feat(web): 分时槽宽会话轴与分钟映射`

---

### Task 4: 刻度与 format 适配

**Files:**
- Modify: `apps/web/src/stock/format.ts`
- Modify: `apps/web/src/stock/format.test.ts`（旧分钟测保留；新增或改 `formatIntradayTickMark` 支持 slot）

- [ ] **Step 1:** `formatIntradayTickMark` / crosshair：根据 `time - BASE` 与**当前 slotSec** 还原 HH:mm（秒可省略除非 S<60）。  
  因 format 函数无 React 状态，改为：

```typescript
export function formatIntradayTickMark(time: Time, slotSec = 60): string
export function formatIntradayCrosshairTime(time: Time, slotSec = 60): string
```

默认 `slotSec=60` 保持旧测通过；StockChart 传入真实 `slotSec`。

- [ ] **Step 2:** `toIntradayChartTime` 可保留分钟版供旧路径；新路径用 slots 模块。  
- [ ] Commit: `feat(web): 分时刻度支持可变槽宽`

---

### Task 5: StockDetailView 双轮询 + 组序列

**Files:**
- Modify: `apps/web/src/stock/StockDetailView.tsx`

- [ ] **Step 1:** 加载 settings：

```typescript
const [slotSec, setSlotSec] = useState(10);
useEffect(() => {
  void api<{ intraday_poll_interval_sec?: number }>("/api/settings").then((s) => {
    setSlotSec(clampIntradayPollIntervalSec(s.intraday_poll_interval_sec));
  });
}, []);
```

- [ ] **Step 2:** 状态：

```typescript
const [livePrice, setLivePrice] = useState<number | null>(null);
const [liveSlotAt, setLiveSlotAt] = useState<number | null>(null);
```

报价轮询（依赖 `slotSec`）：

```typescript
useEffect(() => {
  if (period !== "intraday") return;
  const tick = async () => {
    const q = await api<...>(`/api/market/intraday/quote?...`);
    const last = q[...].last;
    // 用北京现在时分秒 → toAshareSessionSlot(..., slotSec)
    // setLivePrice / setLiveSlotAt；并更新 quote 展示
  };
  void tick();
  const id = setInterval(tick, slotSec * 1000);
  return () => clearInterval(id);
}, [period, normalizedSymbol, slotSec]);
```

分钟补刷：

```typescript
const minuteMs = Math.min(60_000, Math.max(30_000, slotSec * 1000));
// loadBars intraday；setBars；勿整页 loading
```

- [ ] **Step 3:** `chartBars` / 传给图：

```typescript
const slotBars = useMemo(() => {
  let base = mapMinuteBarsToSlots(bars.data ?? [], slotSec);
  if (livePrice != null && liveSlotAt != null) {
    base = upsertSlotPrice(base, liveSlotAt, livePrice);
  }
  return base;
}, [bars.data, slotSec, livePrice, liveSlotAt]);
```

为副图/资金趋势：把 `slotBars` 转回轻量 `OhlcvBar[]`（伪 ts 或仅用 ChartBar 扩展 StockChart 输入）。**推荐** StockChart 分时主路径直接吃 `slotBars: ChartBar[]` + 原始 minute 仅用于摘要；MACD 用 slotBars；fund flow：将 slotBars 映成 `OhlcvBar`（ts 用会话日+槽还原的 ISO，或扩展 `buildIntradayFundFlow` 接受 ChartBar[]——选改动小者：DetailView 生成 `slotOhlcv` 供 fund）。

```typescript
function chartBarsToPseudoOhlcv(bars: ChartBar[], sessionDate: string): OhlcvBar[]
```

warmup/index 仍按分钟拉；fund 计算：warmup 分钟顺序算指标时**不变**；**当日上图序列**用 slot 伪 OHLCV（与主图一致）。即 `buildIntradayFundFlow` 增加可选 `sessionBars: OhlcvBar[]` 覆盖当日段，或调用方传入「warmup 非当日 + 当日 slotOhlcv」拼接。

简化实现（本任务采用）：

- `stockBarsForFund = [...warmupBeforeSession, ...slotOhlcvToday]`
- 指数同样：index warmup 分钟 + 可选 index live 快照补当前槽（有则拉指数 quote）。

- [ ] **Step 4:** 传 `slotSec`、`slotBars`（或让 Chart 内部 map）给 `StockChart`；删除原 15s 固定 interval。
- [ ] Commit: `feat(web): 分时按设置间隔报价补点并驱动副图`

---

### Task 6: StockChart 轴与副图

**Files:**
- Modify: `apps/web/src/stock/StockChart.tsx`

- [ ] **Step 1:** props：`slotSec?: number`（默认 60 兼容）、优先使用父组件传入的已合并 `slotChartBars?: ChartBar[]`；若无则内部 `mapMinuteBarsToSlots(bars, slotSec)`。
- [ ] **Step 2:** placeholders / visibleRange 用 `ashareSessionLastSlot(slotSec)`；auction 线用 `ashareContinuousStartSlot(slotSec)`。
- [ ] **Step 3:** MACD、volume、fund 基于 slot chart bars；`formatIntradayTickMark(time, slotSec)`。
- [ ] **Step 4:** vitest `src/stock/` + Commit `feat(web): StockChart 可变槽宽分时轴`

---

### Task 7: 规格收尾

- 规格状态 → 已实现  
- Commit: `docs: 分时槽宽轮询规格标为已实现`

---

## Spec coverage

| 项 | Task |
|----|------|
| settings 5–60 | T1–T2 |
| 槽宽=间隔 | T3 |
| 分钟铺底+报价补点 | T5 |
| 副图共用 | T5–T6 |
| 分钟慢刷 | T5 |
| 刻度 | T4–T6 |

## 风险备注

- 改 `toChartBars(..., "intraday")` 全局行为易碎；新路径走 `intradaySlots`，旧分钟函数默认 slotSec=60。
- `S` 变化清空 live 补点并重建。
