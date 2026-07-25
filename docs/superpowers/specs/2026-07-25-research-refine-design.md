# 投研精选设计（早盘 + 尾盘）

**日期：** 2026-07-25  
**状态：** 已实现  
**入口：** 早盘选股 / 尾盘选股页；设置 → 投研精选  
**后续增强（同日已落地）：** 必填价格计划、飞书全量字段、预取估值 + 分批/并行无工具 LLM

## 目标

在早盘、尾盘**原筛选落库之后**，用 LLM 对候选个股打 `score` / `confidence` 并给出可执行价格计划，按可配置 TopN 产出精选名单；页面分两段展示；默认可手动触发，设置开关打开后选拔结束自动跑。

## 非目标

- 不下单、不改风控闸门
- 不替代原筛选结果（`morning_strong_picks` / `closing_picks` 仍保留）
- 不改造投研对话页主流程（对话仍走完整 skill + tools）
- 不做跨日回测评估面板（本阶段只做当日精选）
- 不在精选路径加载完整投研 skill 正文或多轮无关工具（已改为预取事实）

## 行为摘要

| 项 | 约定 |
|----|------|
| 范围 | `source ∈ {morning, closing}` |
| 打分 | **主路径**：主线程预取 `get_valuation` 事实 → 按批（默认 4）单次无工具 LLM → JSON 数组；批间可并行（默认 2）。**降级**：批失败则逐只一次无工具调用；无预取事实时最多 3 轮且仅允许 `get_valuation` / `get_financials` |
| 排序 | `confidence >= min_confidence` 后按 `score` 降序取 TopN |
| TopN | 可配置，默认 5 |
| 价格 | 每只必填买入区间、目标价区间、止损价；缺省/非法则该股跳过 |
| 展示 | 上：原筛选（含选拔现价）；下：投研精选（含买入/目标/止损） |
| 触发 | 按钮手动；`research_refine_auto=true` 时选拔成功后自动 |
| 失败 | 单股/单批失败记入 `errors` 并跳过；无 Key/全批失败时明确错误，**不影响**原选拔、不误清空旧精选 |
| 飞书 | 有结果时推送**全量字段**；`category=research`（托管类别，须在允许列表中） |

## 数据流

```
原选拔落库
  → ResearchRefineService.run(source, asof)
  → 候选：按原 score 降序截断至 max_candidates（默认 15）
  → 主线程 prefetch_refine_facts（估值/现价摘要）
  → 分批 score_picks_batch_sync（无 tools）→ JSON 数组
  → parse_score_payload / parse_score_payload_list（强制价格计划）
  → 过滤置信度 → TopN
  → 写入 research_picks（同日同 source 先删后写）
  → 飞书 category=research（全量正文；受总开关 + 类别约束）
```

### 单股 JSON 约定

```json
{
  "symbol": "600519.SH",
  "score": 0,
  "confidence": 0,
  "rationale": "一句话理由",
  "buy_low": 1600,
  "buy_high": 1650,
  "target_low": 1750,
  "target_high": 1850,
  "stop_loss": 1550
}
```

批量输出为上述对象的 **JSON 数组**。亦接受 `buy_range` / `target_range` 二元数组写法。

- `score` / `confidence`：0–100；非法则该股跳过  
- **必填价格**：买入区间、目标价区间、止损价；缺任一或无法解析为正数区间则跳过  
- 数字应基于预取事实归纳；事实缺失时应降低 `confidence`，禁止凭空编造财报数字  
- 解析失败：跳过该股并记入批次 `errors`

## 配置

经现有 Settings / `.env` / 设置页「投研精选」：

| 字段 | 环境变量 | 默认 | 说明 |
|------|----------|------|------|
| `research_refine_top_n` | `RESEARCH_REFINE_TOP_N` | `5` | 精选数量（1–20） |
| `research_refine_min_confidence` | `RESEARCH_REFINE_MIN_CONFIDENCE` | `70` | 置信度门槛（0–100） |
| `research_refine_max_candidates` | `RESEARCH_REFINE_MAX_CANDIDATES` | `15` | 送入打分的候选上限（1–50） |
| `research_refine_auto` | `RESEARCH_REFINE_AUTO` | `false` | 选拔后自动精选 |
| `research_refine_batch_size` | `RESEARCH_REFINE_BATCH_SIZE` | `4` | 每批股票数（1–10） |
| `research_refine_parallel` | `RESEARCH_REFINE_PARALLEL` | `2` | 并行批次数（1–4） |

无 LLM API Key 时：手动精选返回 `llm_api_key_missing`；自动精选仅记日志，不抛垮主选拔。

## 落库

表 `research_picks`（Alembic `0010_research_picks`）：

| 列 | 说明 |
|----|------|
| `asof` | 业务日 |
| `source` | `morning` \| `closing` |
| `symbol` | 规范化代码 |
| `name` | 名称 |
| `score` | LLM 分数 |
| `confidence` | 置信度 |
| `rationale` | 一句话理由 |
| `rank` | 1..N |
| `meta_json` | 含价格计划及原始摘要 |
| `created_at` | 写入时间 |

同 `(asof, source)` 重跑：先删后写。价格字段同时写入 `meta_json`，并由 `list_research_picks` / API / UI 读出。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/morning/research-refine` | 对当日早盘候选跑精选；可选 `asof` |
| POST | `/api/closing/research-refine` | 对当日尾盘候选跑精选 |
| GET | `/api/morning/latest` | 含 `research_picks` |
| GET | `/api/closing/latest` | 含 `research_picks` |

请求体（可选）：可覆盖本次 `top_n` / `min_confidence`（不写回 .env）。

自动触发：`MorningBriefService.run_post_auction` / `ClosingPickService.run` 成功且候选非空、且 `research_refine_auto` 时调用；异常吞掉并打日志。

## UI

### 早盘 / 尾盘页

1. 「强势个股 / 命中个股」表含**选拔现价**（早盘 `price`←竞价 `auction_price`；尾盘 `price`/`last_close`）  
2. 下方「投研精选」：排名、代码、名称、score、confidence、**买入区间 / 目标价 / 止损**、理由  
3. 「投研精选」按钮（busy）；auto 开启时选拔完成后刷新精选段  

### 设置页

「投研精选」：TopN、置信度、候选上限、每批股票数、并行批次数、自动精选开关。  
「飞书告警」：可勾选类别 **投研精选（research）**。

## 飞书

精选成功且有结果时：`category=research`，正文含每只：

- rank / symbol / name  
- score / confidence  
- 买入区间、目标价区间、止损  
- 理由  
- 可选附带少量 `errors` 摘要  

`research` 为**托管类别**（与 morning/closing/paper/risk 并列），须出现在 `FEISHU_ALERT_CATEGORIES`；默认类别含 `research`，不含 `risk`。受总开关约束；测试推送可 `force` 绕过。

## 组件边界

| 单元 | 职责 |
|------|------|
| `ResearchRefineService` | 取候选、预取、分批打分、解析、过滤、落库、飞书 |
| `prefetch_refine_facts` | 压缩估值/现价事实 |
| `NanobotResearchSession.score_picks_batch_sync` | 无工具批量 JSON |
| `NanobotResearchSession.score_pick_json_sync` | 单股快路径 / 短工具降级 |
| morning/closing routes | refine API；latest 附带结果 |
| Settings | 六项精选配置 + 飞书 research 勾选 |
| Morning/Closing 页 | 两段展示 + 按钮 |

## 验收

1. TopN / `min_confidence` / `max_candidates` / `batch_size` / `parallel` 配置生效  
2. 缺价格计划或置信度不足者不进入精选表  
3. 无 API Key 时手动精选有明确错误；原筛选列表仍在  
4. `auto=false` 仅手动；`auto=true` 选拔后出现精选（有 Key 时）  
5. 同日重跑覆盖旧精选  
6. 飞书正文含全量价格字段（总开关与类别开启时）  
7. 单测：解析/过滤/跳过/覆盖/飞书正文；LLM 用 mock  

## 相关迁移与配置

- Alembic：`0010_research_picks`、`0011_auction_price`（早盘现价）  
- `.env.example` 已列出全部精选与飞书相关键（中文注释）
