# 投研精选中文来源 + 按日回看 + Upsert 落库

> 状态：待实现  
> 日期：2026-08-07

## 目标

1. 飞书推送（图片顶栏与文本）将 `投研精选·morning/closing` 展示为 **`投研精选·早盘/尾盘`**。
2. 早盘/尾盘**候选个股（含策略）**与**投研精选**可靠落库，**同键不重复**（允许重跑更新）。
3. 早盘/尾盘页在「投研精选」按钮左侧增加**日期选择**，按所选日回看候选 + 精选。

## 决策摘要

| 项 | 选择 |
|----|------|
| 去重策略 | B：唯一键 upsert；重跑更新，不堆重复行 |
| 策略落库范围 | B：候选 + 精选都存 `strategy_id` |
| 日期回看 | A：早盘/尾盘两页都有；选日刷新候选 + 精选（整页该日数据） |
| 实现路径 | 方案 1：现表增强 + `GET …/latest?asof=`（或尾盘 `/history`） |

## §1 展示文案

- **内部标识不变**：DB / API / `source` 仍为 `morning` | `closing`。
- **对人展示映射**：`morning` → **早盘**，`closing` → **尾盘**。
- **飞书图片顶栏**：`投研精选·早盘` / `投研精选·尾盘`（禁止出现英文 morning/closing）。
- **飞书文本标题/正文**、精选面板等对用户可见处同步中文。
- **日志 / dedupe_key** 可继续使用英文 `source`（如 `research:morning:{asof}`）。

公共映射建议放在一处（如 `source_label(source) -> str`），图片渲染与文本格式共用。

## §2 落库与去重

### 2.1 `research_picks`

- 新增可空列 `strategy_id`（`String(64)`，可索引）。
  - 尾盘：从候选带来（合并去重时保留得分最高候选对应策略）。
  - 早盘：固定标签 `auction_strong`（展示名「竞价强势」）。
- 唯一约束：`(asof, source, symbol)`。
- 落库改为 **upsert**（按唯一键更新 score / confidence / rationale / rank / meta / strategy / name）。
- 同日同源重跑后：删除**本次结果集以外**的旧精选行，避免僵尸行；过程中不产生重复行。
- 废弃「先整批 DELETE 再 INSERT」作为主路径（可保留为空结果时的清理语义）。

### 2.2 `morning_strong_picks`

- 新增可空 `strategy_id`。
  - 个股（`pick_type=stock`）：写入 `auction_strong`。
  - 板块（`board`）：可空或 `board`。
- 唯一约束：`(asof, pick_type, code)`（若尚无）。
- 写入改为 upsert。

### 2.3 `closing_picks`

- 已有 `strategy_id`；补齐唯一约束 `(asof, strategy_id, code)`（若尚无）。
- 写入改为 upsert，同策略同代码不重复。

### 2.4 API 返回

- `list_research_picks` / morning·closing `latest`（及 closing `history`）返回项带 `strategy_id`。
- 可选：能解析策略表时附带可读名；否则前端用 id 或早盘固定中文。

## §3 日期选择与回看 UI

### 位置

- `/morning`、`/closing` Hero 操作区：在右侧「投研精选」按钮**左侧**增加日期控件。
- 风格与现有页面一致（原生 `type="date"` 或现有日期组件均可）。

### 行为

- 默认：当前业务日（与现有 `latest` 日期解析一致）。
- 改日期 → `GET /api/morning/latest?asof=` 或 `GET /api/closing/latest?asof=`（尾盘若需「不做非交易日回退」可用已有 `/history` 对齐），刷新该日：**候选列表 + 投研精选 + 文案区**。
- 选历史日时：「投研精选」按钮仍可对**所选 asof** 触发 refine（允许补跑）。
- 无数据：候选/精选空态「该日暂无数据」，不抛错打断。

### 展示

- 候选与精选行展示策略：有 `strategy_id` 则显示可读名（能解析则策略名/「竞价强势」，否则原 id）。

## 非目标

- 不新建独立归档快照表。
- 不新增独立 `GET /api/research-picks`（本阶段复用 latest/history）。
- 不改变飞书发图通道（仍为上传 + Webhook）。
- 内部 `source` 枚举不改为中文。

## 验收

- 飞书图片顶栏为「投研精选·早盘/尾盘」，无 morning/closing 字样。
- 同日同源同代码精选重跑后库中仍仅一行，字段为最新值；落选旧行被清理。
- 早盘候选带 `auction_strong`；尾盘候选/精选带策略 id；无重复行。
- 早/尾盘页日期控件在「投研精选」左侧；切日可看到该日候选与精选；空日有明确空态。

## 主要改动面（实现指引）

| 区域 | 文件（示意） |
|------|----------------|
| 文案映射 | `desk_ai/research_table_image.py`、`refine.format_research_feishu_body` / `_maybe_feishu` |
| ORM + 迁移 | `desk_db/models.py`、alembic |
| Upsert 写入 | `refine` 落库、`morning_strong` / `closing_pick` 写入路径 |
| API 序列化 | `list_research_picks`、morning/closing routes |
| UI | `Morning.tsx`、`Closing.tsx`、`sessionPick/shared.tsx` |
