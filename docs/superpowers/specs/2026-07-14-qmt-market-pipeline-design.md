# QMT 真实行情管道设计

> 状态：已确认（brainstorming §1–§3）  
> 日期：2026-07-14  
> 范围：本迭代仅落地「真实行情管道」，替换 demo seed 作为日常主路径；不开始实盘下单。

## 1. 目标

将刻度 Desk 的行情主路径从「`POST /api/market/seed` 注入演示 K 线」切换为：

- **QMT / `xtdata` 为主**拉取行情并落库；
- **AkShare 仅**用于历史日线空洞补洞 + 交易日历同步；
- 监控页与下游模块以关系库 `bars_daily` / `bars_minute` 为真相源（分钟仅近 3 个交易日）。

## 2. 现状缺口摘要

| 现状 | 说明 |
|------|------|
| 数据多为 seed | `MarketService.seed_demo_data`、日历/情绪/龙虎榜 seed 路由支撑冒烟与演示；日常无真实拉数主路径 |
| 无 `xtdata` 行情适配 | 仅有 `QmtBroker`/`MockQmtBroker` 交易侧占位，行情未与交易通道分离封装 |
| 无 APScheduler | FastAPI `lifespan` 仅 `create_all`，无日终/盘中/回填定时任务 |
| 日历周末 fallback | `CalendarService.is_trade_day` 无库记录时按「非周末 = 开市」；无节假日真相源 |
| 表已存在但未接真源 | `bars_daily` / `bars_minute` / `trade_calendar` / `watchlist` ORM 与 upsert 日线已有；分钟 ingest / purge / 任务状态 API 尚未落地 |
| 指数配置缺失 | 尚无 `configs/market/indices.yaml` |

## 3. 数据源策略

| 源 | 用途 | 不用于 |
|----|------|--------|
| QMT / `xtdata` | 全 A 日线增量与优先回填；自选∪指数分钟落库；盘中最新价只读补齐 | 交易下单（本迭代） |
| AkShare | 历史日线空洞补洞；交易日历（含节假日）→ `trade_calendar` | 盘中主源；全市场日常日线主拉取 |

符号规范统一走既有 `desk_common.symbols.normalize_symbol`（如 `600519.SH`）。

## 4. 日线方案

- **宇宙**：全 A（可由任务配置收窄为「任务宇宙」，验收时允许配置子集，默认意图为全 A）。
- **落库表**：`bars_daily`，长期保留。
- **策略（已选）**：日终增量 + 历史分块回填；**禁止**每次日终全量重下多年。
  - **日终增量**：交易日约 15:30，拉 **当日 / 近 N 日**（N 可配置，默认建议 1～3）日线 → 批量 upsert。
  - **分块回填**：夜间任务按标的批或日期窗检测缺口；优先 QMT，失败/空洞再 AkShare。
  - **冷启动**：同一套回填流水线，可后台跑并查 `jobs/status` 进度。

## 5. 分钟方案

- **落库表**：`bars_minute`。
- **宇宙**：`watchlist` ∪ `configs/market/indices.yaml` 指数列表（合并去重）。
- **保留窗口**：仅最近 **3 个交易日**（按 `trade_calendar.is_open=true` 计数）；过期按交易日切点滚动删除。切点：取「当前交易日往前数第 4 个交易日」的会话开盘（A 股默认 `09:30`，时区 `Asia/Shanghai`），删除所有 `ts` **严格早于**该时刻的分钟行，避免误删当日与近 3 日。
- **盘中 UI**：近端读库；最新缺口可通过 QMT **只读**补齐（不必立刻写库亦可满足最新价展示）。

## 6. 组件与职责

| 组件 | 职责 |
|------|------|
| `qmt_md`（建议路径 `packages/market/.../qmt_md`） | 封装 `xtdata`：股票列表、日线批量、分钟、快照只读。**与 `QmtBroker` 交易通道严格分离** |
| `DailyBarIngestor` | 全 A 日终增量 → `upsert` `bars_daily` |
| `HistoryBackfill` | 缺口检测 → 优先 QMT，空洞再 AkShare → `bars_daily` |
| `IntradayMonitor` / 分钟 ingest | 自选∪指数分钟写入 `bars_minute`；对外查询时可叠加短 TTL/QMT 最新价补洞 |
| `CalendarSync` | AkShare（或交易所日历接口）→ `trade_calendar`；调度任务经「是否交易日」门闸 |
| APScheduler | 挂在 FastAPI `lifespan`：启动注册、关闭 shutdown |

既有 `MarketService.upsert_daily_bars` 可复用/扩展为批量 upsert；分钟侧对称增加 upsert 与 purge。

## 7. 数据流

```text
                    ┌─────────────────┐
                    │  trade_calendar │◄── CalendarSync ◄── AkShare
                    └────────┬────────┘
                             │ 交易日门闸
                             ▼
QMT xtdata ──日线──► DailyBarIngestor ──upsert──► bars_daily（全 A，长期）
       │                    ▲
       │                    └── HistoryBackfill ◄── 缺口（QMT 优先，AkShare 补洞）
       │
       └──分钟──► 分钟 ingest ──upsert──► bars_minute（自选∪指数，近 3 交易日）
              │                              │
              │                              └── purge_minute_older_than_3td
              └── 最新价只读 ──► GET intraday/quote（可选，不强制落库）

监控/API：GET bars/daily、bars/minute 读库；Overview 不以 seed 为默认主路径
调度：APScheduler（API lifespan）→ 下表各 job
```

## 8. 调度表

时间均可配置（Settings / YAML）；下列为默认意图。带「交易日门闸」的任务在非交易日跳过（日历未同步时见 §10）。

| 任务 ID | 默认时机 | 行为 |
|---------|----------|------|
| `sync_trade_calendar` | 每日凌晨或 API 启动时 | AkShare → upsert `trade_calendar` |
| `ingest_daily_incremental` | 约 15:30（交易日） | QMT 全 A 当日/近 N 日日线 upsert |
| `backfill_daily_chunks` | 夜间低峰（可暂停） | 按批补历史空洞（QMT→AkShare） |
| `ingest_minute_watch` | 盘中每 1～5 分钟 | 自选∪指数分钟 upsert |
| `purge_minute_older_than_3td` | 分钟任务末尾或收盘后 | 按交易日切点删除过期分钟 |

## 9. 幂等与回填

- 日线 / 分钟唯一键均为 `(symbol, ts)`；写入一律 **upsert**（同键覆盖 OHLCV，不堆重复行）。
- 任务可重入：重复执行日终增量不增加行数。
- 回填按 **缺口** 驱动：用 `MAX(ts)`、缺失交易日查询或轻量缺口记录，禁止「无脑全量重下多年」。
- 建议保留简单 **任务运行记录**（成功/失败、处理标的数、耗时、错误列表摘要），供 `GET .../jobs/status` 查询。

## 10. 失败降级

| 场景 | 行为 |
|------|------|
| QMT / `xtdata` 不可用 | 日终/分钟任务标记失败并记日志；可选飞书告警；**不清库**；UI 仍可读已落库日线与近 3 日分钟 |
| 单标的拉取失败 | 跳过并记入任务错误列表，不阻断整批 |
| AkShare 补洞失败 | 该缺口保持「待回填」，下次夜间任务再试 |
| 分钟清理失败 | 下次任务重试；切点见 §5（第 4 个交易日 `09:30` Asia/Shanghai），避免误删当日 |
| 日历未同步 | 仍可周末 fallback 判断交易日，但任务日志必须提示「日历未同步」 |

## 11. 与 demo seed 的关系

- 保留 `POST /api/market/seed`（及测试依赖的其他 seed）供无 QMT 环境冒烟。
- **一键启动 / 实盘日常路径默认不依赖 seed**。
- 真实同步成功后，监控以库内 `bars_*` 为准；Overview「注入演示数据」降为次要入口，并注明会覆盖同键假数据。
- 交易日历：优先 `CalendarSync` 真实日历；无数据时保留现有周末 fallback +「日历未同步」日志。

## 12. API 契约

前缀：`/api/market`（与现有路由风格一致）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/jobs/daily-sync` | 手动触发日终增量（同调度任务逻辑） |
| `POST` | `/jobs/minute-sync` | 手动触发自选∪指数分钟同步 |
| `GET` | `/bars/daily?symbol=&from=&to=` | 读 `bars_daily` |
| `GET` | `/bars/minute?symbol=&from=&to=` | 读 `bars_minute`（常态仅近 3 交易日有数据） |
| `GET` | `/intraday/quote?symbols=` | 可选直连 QMT 最新价补洞 |
| `GET` | `/jobs/status` | 最近任务状态（日终/分钟/回填/日历等） |

**指数配置**：`configs/market/indices.yaml`（如沪深300、上证综指、深成指、创业板指等；具体代码以 QMT 可识别符号为准）。与自选合并去重后作为分钟宇宙。

现有 `POST /api/market/seed`、`GET /watchlist` 等保留；本迭代不强制删 seed。

## 13. 验收标准（DoD）

1. 交易日日终（或手动 `daily-sync`）后，任务宇宙内标的的 **当日日线** 可在 `bars_daily` 查到；重复执行 **不增重复行**。
2. 自选 ∪ 配置指数的分钟写入 `bars_minute`，且库内 **不含** 早于「最近 3 个交易日」的分钟。
3. 监控/API：日线读库；分钟读库；最新价可选 QMT 补洞。
4. QMT 断开时任务失败可观测（status/日志）；已有数据仍可展示。
5. pytest：upsert 幂等、3 交易日 purge、缺口回填选择逻辑（QMT Mock）冒烟通过。

## 14. 本迭代明确不做

- 全 A 分钟落库或全市场分钟订阅持久化
- 真实 QMT 下单 / 把行情逻辑塞进 `QmtBroker`
- 删除全部 seed 接口（可保留测试与无 QMT 冒烟）
- 每次日终全量重下多年日线
- 板块成分实时同步、情绪/龙虎榜真源（不属本管道）
- 港股/期货/融资融券等 v1 已排除范围

## 15. 测试要点（与实现计划衔接）

- Mock `qmt_md`：日线/分钟返回固定序列 → 双次 sync 行数不变。
- 构造 4+ 交易日分钟数据 → purge 后仅剩最近 3 交易日。
- 人为制造日线缺口 → `HistoryBackfill` 先走 QMT Mock，失败路径走 AkShare Mock。
- 日历缺表时门闸日志含「日历未同步」；有真实日历后节假日不触发日终增量。

---

**下一步**：用户审阅本文件通过后，再编写实施计划（writing-plans），然后开写代码。
