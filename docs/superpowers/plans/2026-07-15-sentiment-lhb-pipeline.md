# 打板情绪 + 龙虎榜真源管道 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将打板情绪与龙虎榜从 seed 切换为日终可调度真源：QMT `limitupperformance` 聚合落库 + AkShare 龙虎榜落库，挂现有 JobStore/Scheduler。

**Architecture:** `QmtSentimentClient` + `SentimentAggregator` 写入 `limit_up_*`；`AkshareLhbClient` + `LhbDailyIngestor` 写入 `lhb_*`；`MarketJobs.sync_sentiment_daily` / `sync_lhb_daily` 可观测；API 手动触发；Web 去掉进页自动 seed。

**Tech Stack:** Python、SQLAlchemy、pytest、QMT xtdata（Mock）、AkShare（Fake）、APScheduler、FastAPI、React。

**Spec:** `docs/superpowers/specs/2026-07-15-sentiment-lhb-pipeline-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `packages/sentiment/desk_sentiment/qmt_client.py` | Protocol + Mock + Xtdata stub |
| `packages/sentiment/desk_sentiment/aggregator.py` | 聚合公式 |
| `packages/sentiment/desk_sentiment/ingest.py` | 日终 upsert/快照替换 |
| `packages/sentiment/desk_sentiment/__init__.py` | 保留 snapshot/seed；导出新 API |
| `packages/lhb/desk_lhb/akshare_client.py` | AkShare 适配 + Fake 协议 |
| `packages/lhb/desk_lhb/ingest.py` | 按日替换写入 |
| `packages/lhb/desk_lhb/__init__.py` | 保留 by_date/seed |
| `packages/market/desk_market/jobs.py` | 增 sync_sentiment_daily / sync_lhb_daily |
| `packages/market/desk_market/scheduler.py` | 注册两 job |
| `configs/market/sync.yaml` | cron 默认 |
| `apps/api/app/routes/sentiment_lhb.py` | jobs 路由 |
| `apps/web/src/App.tsx` | 取消强制 seed |
| `tests/test_sentiment_*.py` / `tests/test_lhb_*.py` | TDD |

---

### Task 1: SentimentAggregator 纯聚合（TDD）

**Files:**
- Create: `packages/sentiment/desk_sentiment/aggregator.py`
- Test: `tests/test_sentiment_aggregator.py`

- [ ] **Step 1: 写失败测试** — 给定 Fake 行（涨停 sealed 板高 3、涨停 broken、跌停）断言 count/max/break_rate/promote_rate/ladder
- [ ] **Step 2: pytest 期望 FAIL**
- [ ] **Step 3: 实现 `aggregate_limit_rows(rows) -> {stat, stocks}`**（映射 sealCount→board_height，breakUp>0→broken，promote=板高≥2且sealed/涨停数）
- [ ] **Step 4: pytest PASS**
- [ ] **Step 5: Commit** `feat(sentiment): add limit-up aggregator`

---

### Task 2: QmtSentimentClient Mock + Ingestor 幂等

**Files:**
- Create: `packages/sentiment/desk_sentiment/qmt_client.py`
- Create: `packages/sentiment/desk_sentiment/ingest.py`
- Modify: `packages/sentiment/desk_sentiment/__init__.py`
- Test: `tests/test_sentiment_ingest.py`

- [ ] **Step 1: 测试** — Mock 返回两只股；`SentimentDailyIngestor(db, client, asof).run()` 后 stats/stocks 可查；再跑一遍 stocks 行数不变
- [ ] **Step 2–4: TDD 实现**（按 asof 删 stocks + upsert stat）
- [ ] **Step 5: Commit** `feat(sentiment): daily ingest with snapshot replace`

---

### Task 3: AkShare LHB Client + Ingestor 幂等

**Files:**
- Create: `packages/lhb/desk_lhb/akshare_client.py`
- Create: `packages/lhb/desk_lhb/ingest.py`
- Modify: `packages/lhb/desk_lhb/__init__.py`
- Test: `tests/test_lhb_ingest.py`

- [ ] **Step 1: Fake 返回 daily+seats；ingest 后 by_date 有数据；重跑席位数不变**
- [ ] **Step 2–4: 实现**（删当日旧 seats/daily 再插；机构名关键字粗判）
- [ ] **Step 5: Commit** `feat(lhb): AkShare daily ingest with seat replace`

---

### Task 4: MarketJobs + scheduler + yaml

**Files:**
- Modify: `packages/market/desk_market/jobs.py`
- Modify: `packages/market/desk_market/scheduler.py`
- Modify: `configs/market/sync.yaml`
- Test: `tests/test_sentiment_lhb_jobs.py`

- [ ] **Step 1: Dead sentiment client → sync_sentiment_daily status failed；Fake 成功 → ok**
- [ ] **Step 2–4: 接线 CalendarService 门闸；scheduler dry_run 含新 job_id**
- [ ] **Step 5: Commit** `feat(market): wire sentiment and LHB daily jobs`

---

### Task 5: API + Web seed 降级 + 验收

**Files:**
- Modify: `apps/api/app/routes/sentiment_lhb.py`
- Modify: `apps/web/src/App.tsx`
- Test: `tests/test_sentiment_lhb_api.py`、`tests/test_sentiment_lhb_acceptance.py`

- [ ] **Step 1: POST jobs/sync + GET snapshot/lhb 集成测；验收链路 Mock 全跑**
- [ ] **Step 2–4: 实现路由；Web 不自动 seed**
- [ ] **Step 5: Commit** `feat(api): sentiment/LHB sync jobs and demote seed UI`

---

## Self-review vs Spec

- QMT 情绪 + AkShare 龙虎榜：Task 1–3  
- 日终/Jobs/调度：Task 4  
- 幂等、失败可观测、seed 降级、读 API：Task 2–5  
- 不做盘中刷库 / THS/TDX / akquant  

---

## Execution

用户已确认「开始」。采用 **本会话 executing-plans 直落**（此前 Subagent 易空转）。
