# 投研对话：基本面 / 行业对比 / 估值 / 五步法 — Design

**日期：** 2026-07-19  
**状态：** 已确认（待实现计划）  
**对照：** AISeeValue `pages/tab1_chat.py` + `charles-nanobot` skills（能力对齐，运行时不嵌入）

## 目标

完善刻度 Desk 投研模块，一期交付：

1. **Skill + 大模型**：沿用设置页 LLM（OpenAI 兼容 / DeepSeek 等）与仓库 `skills/`
2. **股票基本面分析**：利润 / 资产负债 / 现金流趋势，ROE、负债率等
3. **行业 / 同行对比**：2～N 只横向对比
4. **估值**：PE/PB/PS、历史分位、相对同行
5. **五步法深度研报**：业务 → 壁垒 → 预期差 → 风险 → 估值（对齐 Charles `write-report` 场景）

**非目标（本期不做）：**

- 嵌入 AISeeValue Charles / Gradio iframe / nanobot `exec` 工作区
- 完整 qwen-agent 风格 tool 折叠 UI
- 对话直通下单或修改 Kill Switch（硬规则不变）

## 决策摘要

| 项 | 选择 |
|----|------|
| 优先级 | 能力优先（分析工具 + skills），UI 够用 |
| 实现路径 | Desk 原生工具链（方案 1） |
| 财务数据 | QMT `xtdata` 优先 → akshare 自动降级 → 本地缓存 |
| 交付节奏 | 一期内做齐基本面 / 对比 / 估值 / 五步法 |
| 联网搜索 | 可选（如 Tavily）；未配置时五步法降级为财务 + 知识库并明示 |

## 架构

```
Web /ai
  → POST /api/ai/chat（流式）
  → NanobotResearchSession（packages/ai）
       · system + skills 摘要 / 按需加载 SKILL.md
       · OpenAI 兼容 tools 循环
  → Tools（只读）
       · get_financials / peer_compare / get_valuation
       · web_search / search_knowledge / save_research_note
  → FinancialService
       · 缓存 → QMT → akshare
```

- 适配层仍在 `packages/ai`；业务财务能力抽到可测服务（建议 `packages/market` 内模块或新建 `packages/research`，实现计划中定路径）。
- 设置页已有 `llm_*`；搜索 Key 可新增设置项或环境变量（实现计划中二选一，默认 env `TAVILY_API_KEY` 可先落地）。

## 财务数据层

### 获取优先级

1. 命中本地缓存（`symbol + table + 报告期窗口`，默认 TTL 7 天）
2. QMT：`download_financial_data` → `get_financial_data`
3. akshare（东方财富财务摘要 / 三大表）降级
4. 全部失败 → 工具返回结构化 `error`，Agent 不得编造财报数字

### QMT 表映射

| QMT table | 用途 |
|-----------|------|
| Balance | 资产负债 |
| Income | 利润 |
| CashFlow | 现金流 |
| Pershareindex | 每股指标 / ROE 等 |
| Capital | 股本（估值） |

### 落库

建议表或等价存储：`financial_snapshots`

- `symbol`, `table`, `period`（报告期）
- `source`：`qmt` | `akshare`
- `payload`：JSON（标准化字段，非原始厂商全量 dump 亦可，但需稳定 schema）
- `fetched_at`（北京时间语义与全站一致；存储可用 UTC）

### 估值输入

- 现价：现有 Desk 行情
- PE/PB/PS：财报字段 + 股本 / 市值推算，或源字段（统一文档化）
- 历史分位：同标的历史估值序列（有缓存则算；不足则标明样本不足）
- 相对同行：调用对比工具同一批财务 + 估值

## Skills

仓库 `skills/` 新增（名称可微调，语义固定）：

| Skill | 职责 |
|-------|------|
| `investment-research` | 场景索引；不确定时先读 |
| `financial-analysis` | 单股财务趋势 → `get_financials` |
| `peer-compare` | 横向对比 → `peer_compare` |
| `valuation` | 估值与分位/相对 → `get_valuation` |
| `write-report` | 五步法写报 → 财务工具 + `web_search` + 可选 `search_knowledge`；可选 `save_research_note` |

保留既有：`desk-readonly`、`knowledge-rag`、`strategy-yaml-author`、`auction-strong-pick`。  
**投研默认不自动调用 `save_strategy_draft`**（用户明确要求写策略草稿时除外）。

Skill 正文风格对齐 AISeeValue（场景表、工作流、示例问法），但执行路径改为 Desk tools，禁止依赖 `python skills/.../scripts/*.py` 的 exec 约定。

## 工具契约（只读）

| Tool | 输入（要点） | 输出（要点） |
|------|--------------|--------------|
| `get_financials` | `symbol`, 可选 `years` | 标准化指标序列 + `source` |
| `peer_compare` | `symbols[]` | 同行指标表 + 缺失列表 |
| `get_valuation` | `symbol`, 可选 `peers[]` | PE/PB/PS、分位、相对 |
| `web_search` | `query` | 摘要列表；未配置 Key 时 error |
| `search_knowledge` | `query` | 既有知识库命中 |
| `save_research_note` | `title`, `body`, `symbols?` | 保存结果（知识库或笔记表，实现计划定） |
| `list_skills` | — | 既有 |

未知工具名 → `{"error":"unknown tool"}`。禁止注册下单 / 解 Kill Switch。

## API

- `GET /api/ai/skills` — 不变，列出全部 skill
- `POST /api/ai/chat` — body：`{ messages: [{role, content}], skill_hint?: string }`；响应流式文本（可含简短 `[tool:name]` 标记）
- `GET /api/ai/financials/{symbol}` — 调试 / 验数，绕过 LLM；query 可含 `years`

Agent 行为：

1. 有 `llm_api_key`：system（身份 + skills 摘要 + 禁止臆造数字）→ tools 循环 → 流式最终答复  
2. 无 key：明确提示配置设置页；可保留极简规则降级（不假装完成五步法）

## 前端（`Research.tsx`）

能力优先、够用即可：

- 左侧：skills 列表 + LLM 是否已配置提示
- 右侧：多轮消息、流式展示、输入框、发送、新会话
- 快捷提示：五步法单股 / 财务趋势 / 同行对比 / 估值（文案对齐 AISeeValue 示例风格）
- 可选 `skill_hint` 随请求发送
- 不做完整 tool `<details>` 折叠壳；工具过程可用行内标记

## 错误与降级

- 未配 LLM → 提示去「设置 → LLM」
- QMT 失败 → akshare；再失败 → 结构化错误
- 未配搜索 → 五步法仍可基于财务 / 知识库，并在答复中说明缺新闻源
- 财报 / 估值数字必须来自工具结果

## 测试

- `FinancialService`：缓存命中；QMT mock 成功；QMT 失败走 akshare；双失败 error
- tools：注册表；未知工具拒绝；结果截断不影响 JSON 可解析
- chat：mock LLM 触发至少一轮 tool call；无 key 路径
- `GET /api/ai/financials/{symbol}` 契约（可用 mock）
- 前端：多轮 `messages` 组装不回归（轻量）

## 风险与约束

- QMT 财务依赖本机客户端登录；CI 必须全程 mock，不得连真 QMT
- akshare / 东财字段可能漂移，标准化层要集中映射并单测关键字段
- 五步法质量依赖模型与搜索；产品承诺是「可跑通流程 + 数字有据」，不是券商级研报

## 验收标准

1. 配置 LLM 后，可用对话完成：单股财务、同行对比、估值、五步法四类问法  
2. 财务数字带 `source`（qmt 或 akshare）；QMT 不可用时自动降级仍能出数（在 akshare 可用前提下）  
3. `skills/` 含上述投研 skills，且 `/api/ai/skills` 可见  
4. 无下单类工具；未配搜索时五步法不崩溃  
5. 调试接口可不经 LLM 拉出某 symbol 财务快照  

## 实现顺序（供计划拆解）

1. FinancialService + 缓存表 + QMT/akshare + 调试 API  
2. tools 注册与 Agent tools 循环  
3. 五个投研 skills  
4. `web_search` + `save_research_note`  
5. Research 页多轮流式 + 快捷提示  
6. 测试与文档（README / hard-rules 如需补一句）
