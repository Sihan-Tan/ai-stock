# 投研精选设计（早盘 + 尾盘）

**日期：** 2026-07-25  
**状态：** 已实现  
**入口：** 早盘选股 / 尾盘选股页；设置项控制 TopN 与自动精选

## 目标

在早盘、尾盘**原筛选落库之后**，用投研 skill + LLM 对候选个股打 `score` / `confidence`，按可配置 TopN 产出精选名单；页面分两段展示；默认可手动触发，设置开关打开后选拔结束自动跑。

## 非目标

- 不下单、不改风控闸门
- 不替代原筛选结果（`morning_strong_picks` / `closing_picks` 仍保留）
- 不改造投研对话页主流程（复用 `NanobotResearchSession` / 工具白名单即可）
- 不做跨日回测评估面板（本阶段只做当日精选）

## 行为摘要

| 项 | 约定 |
|----|------|
| 范围 | `source ∈ {morning, closing}` |
| 打分 | LLM + 投研 skill（`investment-research` 路由下的只读工具），强制 JSON |
| 排序 | `confidence >= min_confidence` 后按 `score` 降序取 TopN |
| TopN | 可配置，默认 5 |
| 展示 | 上：原筛选；下：投研精选 TopN |
| 触发 | 按钮手动；`research_refine_auto=true` 时选拔成功后自动 |
| 失败 | 单股失败跳过；整批无 Key/LLM 失败时明确错误，**不影响**原选拔 |

## 数据流

```
原选拔落库
  → ResearchRefineService.run(source, asof)
  → 候选：按原 score 降序截断至 max_candidates（默认 15）
  → 逐只投研会话 → JSON（含价格计划，见下）
  → 过滤置信度 → TopN
  → 写入 research_picks（同日同 source 先删后写）
  → 可选飞书 category=research（受飞书告警开关约束）
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

- `score` / `confidence`：0–100 数值；非法则该股跳过  
- **必填价格**：买入区间（`buy_low`/`buy_high` 或 `buy_range`）、目标价区间（`target_low`/`target_high` 或 `target_range`）、止损价 `stop_loss`；缺任一或区间倒置则该股跳过  
- 数字必须来自工具结果的归纳，禁止编造财报数字（与现有投研硬约束一致）  
- 工具返回 `error` 或 JSON 解析失败：跳过该股并记入批次 `errors`

## 配置

经现有 Settings / `.env` / 设置页：

| 字段 | 环境变量 | 默认 | 说明 |
|------|----------|------|------|
| `research_refine_top_n` | `RESEARCH_REFINE_TOP_N` | `5` | 精选数量（1–20） |
| `research_refine_min_confidence` | `RESEARCH_REFINE_MIN_CONFIDENCE` | `70` | 置信度门槛（0–100） |
| `research_refine_max_candidates` | `RESEARCH_REFINE_MAX_CANDIDATES` | `15` | 送入 LLM 的候选上限（1–50） |
| `research_refine_auto` | `RESEARCH_REFINE_AUTO` | `false` | 选拔后自动精选 |

无 LLM API Key 时：手动精选返回明确错误；自动精选仅记日志，不抛垮主选拔。

## 落库

新表 `research_picks`：

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
| `meta_json` | 原始 JSON / 工具摘要等 |
| `created_at` | 写入时间 |

同 `(asof, source)` 重跑：先删后写。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/morning/research-refine` | 对当日早盘候选跑精选；可选 `asof` |
| POST | `/api/closing/research-refine` | 对当日尾盘候选跑精选 |
| GET | `/api/morning/latest` | 增加 `research_picks` |
| GET | `/api/closing/latest` | 增加 `research_picks` |

请求体（可选）：可覆盖本次 `top_n` / `min_confidence`（不写回 .env，仅本次）。

自动触发：`MorningBriefService.run_post_auction` / `ClosingPickService.run` 成功且候选非空、且 `research_refine_auto` 时调用 `ResearchRefineService`；异常吞掉并打日志。

## UI

### 早盘 / 尾盘页

1. 保留现有「强势个股 / 命中个股」表  
2. 下方新增「投研精选」面板：排名、代码、名称、score、confidence、理由  
3. 操作：「投研精选」按钮（busy 态）；auto 开启时选拔完成后自动刷新精选段  

### 设置页

新增一组「投研精选」：TopN、置信度门槛、候选上限、自动精选开关。

## 飞书（可选）

精选成功且有结果时：`FeishuWebhookChannel.send`，`category=research`。  
`research` 为未知托管类别时按现有规则：总开关开则放行；若后续要静音，可纳入托管类别列表（本阶段不强制改飞书开关 UI）。

## 组件边界

| 单元 | 职责 |
|------|------|
| `ResearchRefineService` | 取候选、调会话、解析、过滤、落库 |
| `NanobotResearchSession` | 现有投研循环；精选调用时固定 skill 集合与 JSON 输出约束 |
| morning/closing routes | 暴露 refine API；latest 附带结果；auto 钩子 |
| Settings | 四项配置读写 |
| Morning/Closing 页 | 两段展示 + 按钮 |

## 验收

1. TopN / `min_confidence` / `max_candidates` 配置生效  
2. 置信度不足者不进入精选表  
3. 无 API Key 时手动精选有明确错误；原筛选列表仍在  
4. `auto=false` 仅手动；`auto=true` 选拔后出现精选（有 Key 时）  
5. 同日重跑覆盖旧精选  
6. 单测：过滤排序、单股失败跳过、重跑覆盖；LLM 用 mock  

## 实现要点（实现阶段）

- ORM + alembic/ensure 表  
- `packages/` 下新建精选服务（或挂在 `desk_ai` / 独立小包，实现计划锁定）  
- 设置字段接入 `settings_store`  
- 前端两页 + 设置 Tab/区块  
- 文档与单测
