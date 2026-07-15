# 打板情绪 + 龙虎榜真源管道设计

> 状态：已确认（brainstorming §1–§3）  
> 日期：2026-07-15  
> 前置：QMT 行情管道已落地（日线/分钟/Jobs）；本迭代替换 sentiment/lhb 的 seed 主路径。

## 1. 目标

将「打板情绪」「龙虎榜」从 `seed_demo` 演示路径切换为可调度的日终落库：

| 能力 | 主源 | 落库 |
|------|------|------|
| 打板情绪 | QMT `xtdata` 周期 `limitupperformance` + 自算汇总 | `limit_up_stats` / `limit_up_stocks`（按日快照） |
| 龙虎榜 | AkShare | `lhb_daily` / `lhb_seats` |

- 粒度：**仅日终快照**（不做盘中分钟级刷库）
- 调度：复用 `MarketJobs` + `JobStore` + 交易日门闸 + APScheduler
- 晨会 `run_preopen` **继续只读表**，不改打分真相源
- **不加 akquant**（与 v1「唯一回测内核 backtrader」冲突；且不提供情绪/龙虎榜数据）
- **不以**同花顺/通达信本地客户端为主源

## 2. 现状摘要

| 项 | 现状 |
|----|------|
| `desk_sentiment` / `desk_lhb` | 仅 `snapshot`/`by_date` + `seed_demo` |
| API `sentiment_lhb` | seed + 读接口 |
| Web | 进页常先 seed |
| 真实拉取 | 无 QMT/AkShare 情绪龙虎榜流水线 |
| 可复用 | `JobStore`、`MarketJobs`、scheduler、`SecurityMeta` 在市宇宙 |

## 3. 架构与数据流

```text
QMT limitupperformance → SentimentAggregator → limit_up_stats + limit_up_stocks
AkShare LHB            → LhbDailyIngestor    → lhb_daily + lhb_seats
MarketJobs + 交易日门闸 → sync_sentiment_daily / sync_lhb_daily → JobStore
Web / 晨会             → 只读 DB
```

### 组件

| 组件 | 职责 |
|------|------|
| `QmtSentimentClient` | 封装个股 `limitupperformance`；提供 `MockQmtSentimentClient` |
| `SentimentAggregator` | 聚合字段 → upsert 统计 + 个股表 |
| `AkshareLhbClient` | 按日拉上榜与席位；测试 Fake 注入 |
| `SentimentDailyIngestor` / `LhbDailyIngestor` | 编排拉取与幂等写入 |
| `MarketJobs.sync_sentiment_daily` / `sync_lhb_daily` | JobStore 可观测 |
| 调度 | `configs/market/sync.yaml` 增加两 job；挂现有 scheduler |

情绪客户端可放在 `packages/sentiment`（推荐，领域内聚）或薄封装调用 `desk_market.qmt_md`；**禁止**把该逻辑塞进 `QmtBroker`。

## 4. 字段与聚合约定

### 4.1 情绪个股 `limit_up_stocks`

| 库字段 | 映射 |
|--------|------|
| `board_height` | `sealCount`（几板） |
| `status` | 破板/开板规则 → `broken`，否则 `sealed`（字段细则实现时钉死并单测） |
| `seal_amount` | `upAmount`，缺省 0 |
| `symbol` | `normalize_symbol` |
| `name` | 列表元数据补全，可空 |
| `concept` | 本期允许空字符串 |

### 4.2 情绪汇总 `limit_up_stats`（`asof` 唯一）

| 字段 | 计算 |
|------|------|
| `limit_up_count` | 当日涨停样本数（`direct` 涨停） |
| `limit_down_count` | 当日跌停样本数 |
| `max_board` | `board_height` 最大 |
| `break_rate` | broken / limit_up_count（分母 0 → 0） |
| `promote_rate` | **简化**：当日 `board_height≥2` 且 `sealed` 数 / 涨停数（非严格「昨晋今」；文档与 UI 不宣称精确晋级率） |

**宇宙**：优先 `SecurityMeta` 中 `is_delisted=False`；空则 `list_a_share_symbols(include_delisted=False)`。

### 4.3 龙虎榜

- `lhb_daily`：`asof, symbol, name, reason, net_buy`
- `lhb_seats`：`lhb_id, side(buy|sell), seat_name, amount, is_institution`（席位名关键字粗判机构）
- AkShare 具体函数名在实现时锁定一种稳定接口，经 `AkshareLhbClient` 集中映射，测试只打 Fake

## 5. 幂等

| 表 | 策略 |
|----|------|
| `limit_up_stats` | 按 `asof` upsert |
| `limit_up_stocks` | 按 `asof` **先删后插**（全日快照替换） |
| `lhb_daily` + `lhb_seats` | 按 `asof` 删除旧 seats（经当日 daily id）与 daily 后重插；或等价 upsert，保证重跑不堆席位 |

## 6. 调度与 API

| job_id | 默认时机 | 行为 |
|--------|----------|------|
| `sync_sentiment_daily` | ~15:35 交易日 | QMT 聚合落库 |
| `sync_lhb_daily` | ~18:00 交易日 | AkShare 落库（披露较晚） |

手动：

- `POST /api/sentiment/jobs/sync`
- `POST /api/lhb/jobs/sync`
- 状态：复用 `MarketJobRun`（可按 `job_id` 过滤）

只读保留：

- `GET /api/sentiment/snapshot?asof=`
- `GET /api/lhb?date=`

`POST .../seed` 保留为次要冒烟；Web 进页不自动 seed，无数据时提示。

**可选本迭代**：连板高度新高、自选上榜 → 飞书；无 webhook 只写 `alerts`。

## 7. 失败与降级

- QMT 不可用 / 大批失败：任务 `failed`，**不清库**；页可读最近成功 `asof`
- 单标的失败：记 errors，汇总基于成功样本，message 注明覆盖率
- AkShare 失败：任务 `failed`，保留库内既有日；同 `asof` 可重跑覆盖
- 非交易日：`ok` + `skipped_non_trade_day`

## 8. 验收 DoD

1. 日终或手动后，当日情绪统计一行 + 个股列表可查；重跑快照语义稳定  
2. 当日龙虎榜 + 席位可查；重跑不堆重复席位  
3. pytest：Mock QMT 聚合、Fake AkShare 幂等、任务失败可观测  
4. 读 API/页不依赖自动 seed；无数据有明确提示  
5. 晨会 preopen 在有快照时仍能读到涨停数/最高板  

## 9. 明确不做

- 盘中分钟情绪落库  
- 同花顺 / 通达信本地主源  
- akquant / 第二套回测引擎  
- 严格「昨晋今」晋级率（本期简化）  
- 实盘下单、改晨会竞价选拔逻辑  

## 10. 测试要点

- `SentimentAggregator` 纯函数/服务：给定 Fake 行 → stats/stocks  
- `asof` 快照替换幂等  
- LHB 重跑席位数量稳定  
- `DeadMd` / 抛错客户端 → JobStore `failed`  
- 非交易日 skip  

## 11. 文档与配置

- `configs/market/sync.yaml` 增加两 job cron  
- README 短述：情绪 QMT、龙虎榜 AkShare、与 seed 关系  
- 本文件路径：`docs/superpowers/specs/2026-07-15-sentiment-lhb-pipeline-design.md`
