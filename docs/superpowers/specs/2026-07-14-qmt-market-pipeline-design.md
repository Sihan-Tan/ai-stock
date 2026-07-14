# QMT 真实行情管道设计

> 状态：已确认（brainstorming §1–§3）；**2026-07-14 增补**：日线起始日、退市过滤、前/后复权双存（待用户再审）  
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
| 日线表仅一套 OHLCV | 现有 `BarDaily`：`open/high/low/close/volume/amount` + `adj_factor`；本迭代需迁移为**前复权 + 后复权双套字段**（见 §4.3） |
| 指数配置缺失 | 尚无 `configs/market/indices.yaml` |
| 日线起始日 / 退市策略 | 尚无显式配置与过滤约定（本迭代补齐，见 §4.1、§4.2） |

## 3. 数据源策略

| 源 | 用途 | 不用于 |
|----|------|--------|
| QMT / `xtdata` | 全 A 日线增量与优先回填；自选∪指数分钟落库；盘中最新价只读补齐；证券列表与退市状态识别 | 交易下单（本迭代） |
| AkShare | 历史日线空洞补洞；交易日历（含节假日）→ `trade_calendar` | 盘中主源；全市场日常日线主拉取 |

符号规范统一走既有 `desk_common.symbols.normalize_symbol`（如 `600519.SH`）。

**一致性约束（本迭代不变）**：

- 全 A **日线长期落库**（受 §4.1 起始日下界约束，且排除退市新写入，见 §4.2）。
- **分钟仅自选 ∪ 指数**，仅保留近 **3 个交易日**。
- 行情以 **QMT 为主、AkShare 仅补洞**（日历同理走 AkShare）。

## 4. 日线方案

- **宇宙**：全 A（可由任务配置收窄为「任务宇宙」，验收时允许配置子集，默认意图为全 A）；**新建同步不包含已退市标的**（§4.2）。
- **落库表**：`bars_daily`，长期保留。
- **策略（已选）**：日终增量 + 历史分块回填；**禁止**每次日终全量重下多年。
  - **日终增量**：交易日约 15:30，拉 **当日 / 近 N 日**（N 可配置，默认建议 1～3）日线 → 批量 upsert。日终增量**只补近端**，**不受**「把历史补到起始日之前」影响；也不要求为了对齐起始日而回头重下多年。
  - **分块回填**：夜间任务按标的批或日期窗检测缺口；优先 QMT，失败/空洞再 AkShare。回填窗口下界 = `daily_start_date`（§4.1）。
  - **冷启动**：同一套回填流水线，可后台跑并查 `jobs/status` 进度；历史也不早于 `daily_start_date`。

### 4.1 日线下载起始日期

| 项 | 约定 |
|----|------|
| 配置项 | Settings：`MARKET_DAILY_START`；YAML：`configs/market/sync.yaml` → `daily_start_date`（二者以项目现有配置加载约定为准，文档要求语义一致） |
| 默认示例 | `2018-01-01`（**可改**；验收/生产可按磁盘与回测需求调整） |
| 回填 / 全 A 历史拉取 | 请求与缺口检测的日期下界均 **不早于** `daily_start_date` |
| 日终增量 | **不受**「为补齐 `daily_start_date` 之前历史」驱动；只拉当日/近 N 日 |
| 查询 API | 可不强制裁剪读库结果；写入侧保证不主动拉取起始日之前历史即可 |

### 4.2 退市股票不入库

| 场景 | 策略 |
|------|------|
| 证券列表同步 | **过滤已退市**：全 A 宇宙 / 新建日线与分钟同步任务**不写入**退市标的 |
| 已在库中的退市标的历史日线 | **保留**既有 `bars_daily` 行（不清库）；**停止日线更新** |
| 全 A 宇宙 | 退市后 **不再纳入** 后续增量 / 回填批（可选：在证券元数据表打 `is_delisted` / `status` 标记，便于 API 与选股排除；若本期无独立证券表，至少在同步列表缓存层过滤） |
| 分钟 / 自选 | 若自选仍含退市码：分钟可跳过拉取；UI 可展示「已退市」提示（非本迭代硬性，以实现时最小改动为准） |

**QMT / 退市识别**：以 `xtdata` 证券列表状态 / `InstrumentStatus`（或等价字段）为准；实现时对接真实枚举并 **单测用 Mock 固定状态码**。具体字段名以 QMT 文档与联调为准，本 spec 不锁死字符串常量。

### 4.3 前复权 + 后复权双存（默认前复权）

**现状**：`BarDaily` 仅一套 `open/high/low/close/volume/amount` + `adj_factor`。

**目标（推荐宽表同键双套，避免 `(symbol, ts, adj_type)` 复杂化唯一键）**：

| 字段组 | 含义 |
|--------|------|
| `open_qfq`, `high_qfq`, `low_qfq`, `close_qfq` | 前复权 OHLC |
| `open_hfq`, `high_hfq`, `low_hfq`, `close_hfq` | 后复权 OHLC |
| `volume`, `amount` | 成交量/额（两套价共用；若源对复权量有差异，以 QMT 文档为准并在实现注记） |
| （可选保留）`adj_factor` | 若仍有单因子用途可保留；**不以**「一套价 × 因子」代替双套落库 |

迁移要点：

- 唯一键仍为 `(symbol, ts)`；upsert 同键覆盖**两套** OHLCV。
- 旧列 `open/high/low/close`：**迁移为** `_qfq` / `_hfq` 双套后删除或短暂兼容期映射到前复权（实现计划写清 Alembic/SQL 步骤）；本迭代完成后读路径不依赖未标注复权的裸列。
- **未复权价**：本期**可以不存**（除非实现时发现与双复权同一次拉取几乎零成本，则可选落库；默认范围不含未复权）。

**消费约定**：

| 场景 | 默认 | 可切换 |
|------|------|--------|
| 策略选股 / 回测 | **前复权（qfq）** | 配置或参数切 **后复权（hfq）** |
| DataFeed → backtrader `PandasData` | 默认取前复权列映射到 open/high/low/close | 同上可配置 |
| `GET /bars/daily` | 默认可返回 qfq（或同时返回双套，由契约定一种）；若带 `adj=hfq` 则读后复权列 | 查询参数或响应字段约定在实现时固化 |

拉取侧：QMT/`xtdata` 日线请求需显式取前复权与后复权（或等价两次/带复权参数一次解析为两套）；AkShare 补洞路径对齐同一字段语义后再 upsert。

## 5. 分钟方案

- **落库表**：`bars_minute`。
- **宇宙**：`watchlist` ∪ `configs/market/indices.yaml` 指数列表（合并去重）；**排除退市**（与 §4.2 一致）。
- **保留窗口**：仅最近 **3 个交易日**（按 `trade_calendar.is_open=true` 计数）；过期按交易日切点滚动删除。切点：取「当前交易日往前数第 4 个交易日」的会话开盘（A 股默认 `09:30`，时区 `Asia/Shanghai`），删除所有 `ts` **严格早于**该时刻的分钟行，避免误删当日与近 3 日。
- **盘中 UI**：近端读库；最新缺口可通过 QMT **只读**补齐（不必立刻写库亦可满足最新价展示）。
- **复权**：分钟本迭代**不要求**双复权落库（体量与用途以盘中监控为主）；若展示涨跌依赖日线，仍读 `bars_daily` 前复权。

## 6. 组件与职责

| 组件 | 职责 |
|------|------|
| `qmt_md`（建议路径 `packages/market/.../qmt_md`） | 封装 `xtdata`：股票列表（含退市/InstrumentStatus）、日线批量（前+后复权）、分钟、快照只读。**与 `QmtBroker` 交易通道严格分离** |
| 证券列表同步 | 过滤退市；产出「可交易/在市」全 A 宇宙供日终与回填；可选标记库内退市标的 |
| `DailyBarIngestor` | 全 A（在市）日终增量 → `upsert` `bars_daily`（双套复权） |
| `HistoryBackfill` | 缺口检测（下界 `daily_start_date`）→ 优先 QMT，空洞再 AkShare → `bars_daily` |
| `IntradayMonitor` / 分钟 ingest | 自选∪指数分钟写入 `bars_minute`；对外查询时可叠加短 TTL/QMT 最新价补洞 |
| `CalendarSync` | AkShare（或交易所日历接口）→ `trade_calendar`；调度任务经「是否交易日」门闸 |
| DataFeed（回测边界） | 默认前复权列 → `PandasData`；可配置后复权 |
| APScheduler | 挂在 FastAPI `lifespan`：启动注册、关闭 shutdown |

既有 `MarketService.upsert_daily_bars` 需扩展为双套复权字段批量 upsert；分钟侧对称增加 upsert 与 purge。

## 7. 数据流

```text
                    ┌─────────────────┐
                    │  trade_calendar │◄── CalendarSync ◄── AkShare
                    └────────┬────────┘
                             │ 交易日门闸
                             ▼
证券列表(xtdata) ──过滤退市──► 全 A 在市宇宙
                             │
QMT xtdata ──日线(qfq+hfq)──► DailyBarIngestor ──upsert──► bars_daily（全 A 在市，长期；≥ daily_start_date）
       │                    ▲
       │                    └── HistoryBackfill ◄── 缺口（QMT 优先，AkShare 补洞；不下探起始日之前）
       │
       └──分钟──► 分钟 ingest ──upsert──► bars_minute（自选∪指数，近 3 交易日）
              │                              │
              │                              └── purge_minute_older_than_3td
              └── 最新价只读 ──► GET intraday/quote（可选，不强制落库）

消费：选股/回测/DataFeed 默认读前复权列；可配置后复权
监控/API：GET bars/daily、bars/minute 读库；Overview 不以 seed 为默认主路径
调度：APScheduler（API lifespan）→ 下表各 job
配置：MARKET_DAILY_START / configs/market/sync.yaml::daily_start_date
```

## 8. 调度表

时间均可配置（Settings / YAML）；下列为默认意图。带「交易日门闸」的任务在非交易日跳过（日历未同步时见 §10）。

| 任务 ID | 默认时机 | 行为 |
|---------|----------|------|
| `sync_trade_calendar` | 每日凌晨或 API 启动时 | AkShare → upsert `trade_calendar` |
| `sync_security_list` | 每日或日终前 | xtdata 证券列表 → 过滤退市 → 刷新全 A 在市宇宙（可选写元数据标记） |
| `ingest_daily_incremental` | 约 15:30（交易日） | QMT 全 A **在市** 当日/近 N 日日线（qfq+hfq）upsert；**不**为起始日回补历史 |
| `backfill_daily_chunks` | 夜间低峰（可暂停） | 按批补历史空洞（≥ `daily_start_date`；QMT→AkShare）；跳过退市 |
| `ingest_minute_watch` | 盘中每 1～5 分钟 | 自选∪指数分钟 upsert（跳过退市） |
| `purge_minute_older_than_3td` | 分钟任务末尾或收盘后 | 按交易日切点删除过期分钟 |

## 9. 幂等与回填

- 日线 / 分钟唯一键均为 `(symbol, ts)`；写入一律 **upsert**（同键覆盖双套复权 OHLCV / 分钟 OHLCV，不堆重复行；**不**采用 `adj_type` 分行）。
- 任务可重入：重复执行日终增量不增加行数。
- 回填按 **缺口** 驱动：用 `MAX(ts)`、缺失交易日查询或轻量缺口记录，禁止「无脑全量重下多年」；缺口区间裁剪到 `[daily_start_date, …]`。
- 退市标的：不进入新缺口批；已有历史行保留、不再更新。
- 建议保留简单 **任务运行记录**（成功/失败、处理标的数、耗时、错误列表摘要），供 `GET .../jobs/status` 查询。

## 10. 失败降级

| 场景 | 行为 |
|------|------|
| QMT / `xtdata` 不可用 | 日终/分钟任务标记失败并记日志；可选飞书告警；**不清库**；UI 仍可读已落库日线与近 3 日分钟 |
| 单标的拉取失败 | 跳过并记入任务错误列表，不阻断整批 |
| AkShare 补洞失败 | 该缺口保持「待回填」，下次夜间任务再试 |
| 分钟清理失败 | 下次任务重试；切点见 §5（第 4 个交易日 `09:30` Asia/Shanghai），避免误删当日 |
| 日历未同步 | 仍可周末 fallback 判断交易日，但任务日志必须提示「日历未同步」 |
| 复权某一侧缺失 | 记错误列表；实现策略二选一并在代码注记：整行跳过 **或** 允许另一侧先写、待补（推荐：同行双套齐备再 upsert，避免半截复权行） |

## 11. 与 demo seed 的关系

- 保留 `POST /api/market/seed`（及测试依赖的其他 seed）供无 QMT 环境冒烟。
- **一键启动 / 实盘日常路径默认不依赖 seed**。
- 真实同步成功后，监控以库内 `bars_*` 为准；Overview「注入演示数据」降为次要入口，并注明会覆盖同键假数据。
- seed 演示数据应写入**双套复权字段**（可用相同数字填 qfq/hfq）以免读路径报缺列。
- 交易日历：优先 `CalendarSync` 真实日历；无数据时保留现有周末 fallback +「日历未同步」日志。

## 12. API 契约

前缀：`/api/market`（与现有路由风格一致）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/jobs/daily-sync` | 手动触发日终增量（同调度任务逻辑） |
| `POST` | `/jobs/minute-sync` | 手动触发自选∪指数分钟同步 |
| `POST` | `/jobs/backfill` | 可选：手动触发分块回填（尊重 `daily_start_date`） |
| `GET` | `/bars/daily?symbol=&from=&to=&adj=` | 读 `bars_daily`；`adj` 默认 `qfq`，可选 `hfq`（或同时返回双套，实现定一种并文档化） |
| `GET` | `/bars/minute?symbol=&from=&to=` | 读 `bars_minute`（常态仅近 3 交易日有数据） |
| `GET` | `/intraday/quote?symbols=` | 可选直连 QMT 最新价补洞 |
| `GET` | `/jobs/status` | 最近任务状态（日终/分钟/回填/日历/证券列表等） |

**配置文件**：

- `configs/market/indices.yaml`：沪深300、上证综指、深成指、创业板指等；与自选合并去重后作为分钟宇宙。
- `configs/market/sync.yaml`：至少含 `daily_start_date`（示例默认 `2018-01-01`，可改）、日终近 N 日、批大小等。

现有 `POST /api/market/seed`、`GET /watchlist` 等保留；本迭代不强制删 seed。

## 13. 验收标准（DoD）

1. 交易日日终（或手动 `daily-sync`）后，**在市**任务宇宙内标的的 **当日日线**可在 `bars_daily` 查到，且同行含 **前复权与后复权** 字段；重复执行 **不增重复行**。
2. 回填 / 冷启动历史拉取 **不早于** `daily_start_date`；日终增量即使历史未回满起始日，也只拉近端、不回补起始日之前。
3. 证券列表同步后，**退市标的不被新建写入**；已在库退市标的日线停止更新。
4. 自选 ∪ 配置指数的分钟写入 `bars_minute`，且库内 **不含** 早于「最近 3 个交易日」的分钟。
5. 监控/API：日线读库（默认前复权）；分钟读库；最新价可选 QMT 补洞。
6. DataFeed/回测默认映射前复权列；配置可切后复权。
7. QMT 断开时任务失败可观测（status/日志）；已有数据仍可展示。
8. pytest：upsert 幂等（双套字段）、3 交易日 purge、缺口回填下界、退市过滤（Mock InstrumentStatus）、QMT→AkShare 冒烟通过。

## 14. 本迭代明确不做

- 全 A 分钟落库或全市场分钟订阅持久化
- 真实 QMT 下单 / 把行情逻辑塞进 `QmtBroker`
- 删除全部 seed 接口（可保留测试与无 QMT 冒烟）
- 每次日终全量重下多年日线；或日终为「对齐起始日」回头全量重下
- **未复权**日线落库（可选例外：同一次拉取零成本才考虑；默认不做）
- 以 `adj_type` 分行存复权（已否决，用宽表双套）
- 主动删除已退市标的的历史 `bars_daily`
- 板块成分实时同步、情绪/龙虎榜真源（不属本管道）
- 港股/期货/融资融券等 v1 已排除范围

## 15. 测试要点（与实现计划衔接）

- Mock `qmt_md`：日线返回固定 qfq/hfq 序列 → 双次 sync 行数不变，双套字段被覆盖更新。
- 构造 `daily_start_date` 之前的缺口 → 回填**不请求**该区间；日终增量 Mock 断言参数仅为近 N 日。
- Mock 证券列表含退市状态 → 同步宇宙与 ingest **跳过**退市码；已有退市 symbol 行不被 upsert 更新。
- 构造 4+ 交易日分钟数据 → purge 后仅剩最近 3 交易日。
- 人为制造日线缺口 → `HistoryBackfill` 先走 QMT Mock，失败路径走 AkShare Mock。
- DataFeed：默认读 `_qfq`；切 `hfq` 后映射列切换。
- 日历缺表时门闸日志含「日历未同步」；有真实日历后节假日不触发日终增量。

---

**下一步**：请用户再审阅本节增补（起始日、退市、双复权）通过后，再编写实施计划（writing-plans），然后开写代码。
