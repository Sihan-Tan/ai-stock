# 早盘/尾盘选股附带持仓建议

> 状态：已确认设计，待实现

## 目标

在**尾盘选股**与**早盘竞价强势选拔**完成后，对当前持仓给出操作建议（含理由），与选股结果**合并为同一条飞书推送**。建议仅供参考，**不下单**。

## 决策摘要

| 项 | 选择 |
|----|------|
| 架构 | 方案 1：共享模块 `positions_advice`，挂到现有 run 末尾 |
| 生成模式 | 可配置：`llm`（纯 LLM）或 `hybrid`（规则候选 + LLM 理由） |
| 持仓源 | 设置可选 `live` / `paper`，默认 `live` |
| 早盘挂点 | 仅 `run_post_auction`；`run_preopen` 不做 |
| 尾盘动作 | `持有` / `卖出` |
| 早盘动作 | `持有` / `卖出` / `高抛低吸` / `低吸` |
| 失败策略 | 选股照常推；建议段降级文案（无持仓 / 生成失败） |

## 非目标

- 自动下单或改仓
- 开盘前篇持仓建议
- 新建飞书 alert category（仍用 `morning` / `closing`）
- 「建议 vs 次日成交」回测闭环
- 强制持仓必须绑定策略才能出建议

## 架构

### 新包 `packages/positions_advice/desk_positions_advice/`

| 单元 | 职责 |
|------|------|
| `service.advise_advice(...)` | 编排：读持仓 →（可选）规则候选 → LLM → 结构化结果 |
| `positions.load(source)` | `live`（优先 QMT，失败回退本地）或 `paper`；复用 `BrokerService` |
| `rules.candidates(...)` | 仅 `hybrid`：涨跌幅/成本等简单规则出候选动作 |
| `llm.generate(...)` | 预取事实 + 一次无工具 LLM；解析 JSON；动作落入场景枚举 |
| `format.append_to_push(content, advice)` | 拼「持仓建议」段到飞书/brief 正文 |

### 挂点

1. `ClosingPickService.run`：选股落库并拼选股摘要后 → `advise_advice` → 拼正文 → **一次**飞书「尾盘选股」
2. `MorningBriefService.run_post_auction`：竞价选拔后同理 → **一次**飞书「早盘·竞价强势」
3. 不修改选股主扫描逻辑；建议失败不回滚 picks

### 设置（Settings + env）

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| `positions_advice_enabled` | bool | `true` | 总开关；关闭则与现网一致只推选股 |
| `positions_advice_mode` | `llm` \| `hybrid` | `llm` | A / C |
| `positions_advice_source` | `live` \| `paper` | `live` | 持仓源 |

Settings UI：在现有设置页增加上述三控件（与 `review_auto` 同类持久化）。

## 数据流

1. 现有选股逻辑照常执行并写入 picks / brief 选股字段。
2. `positions_advice_enabled=false` → 跳过建议，推送与现网一致。
3. 按 `positions_advice_source` 读持仓。
4. **无持仓**：建议段「当前无持仓，跳过建议」；选股仍推。
5. **有持仓**：组装事实包  
   - 公共：symbol、数量、成本、现价/浮盈、绑定 strategy_id（若有）  
   - 尾盘：当日涨跌、是否出现在本次选股命中、可选情绪摘要  
   - 早盘：竞价涨幅/额（若在快照中）、板块、情绪、开盘相关字段  
   - `hybrid`：附加 `rule_candidate`（动作 + 规则说明）
6. LLM 一次调用，期望 JSON：

```json
{
  "items": [{ "symbol": "600000.SH", "action": "卖出", "reason": "…" }],
  "market_note": "可选一句市场总评"
}
```

   - 尾盘 `action ∈ {持有, 卖出}`  
   - 早盘 `action ∈ {持有, 卖出, 高抛低吸, 低吸}`  
   - 非法 action → 回退 `持有`，reason 注明回退原因  
7. LLM / 解析失败：建议段「持仓建议生成失败：{简短原因}」；选股仍推。  
8. 正文 = 选股摘要 + 建议段；`extras.positions_advice` 存结构化结果；`alert.send` 一次。

### 持仓截断

持仓超过 N 只（默认 **20**）时，按市值降序取前 N（无市值则按 `|浮盈|` 降序），文末注明「已截断」；N 为代码常量，首版不做设置项。

## 推送文案

```
【尾盘选股】{asof}
…
（原有选股摘要）

—— 持仓建议（live）——
600000.SH 卖出｜冲高回落且尾盘量能转弱，不宜隔夜
601318.SH 持有｜回撤未破成本区，策略卖点未触发
```

早盘结构相同，标题仍为竞价强势相关前缀，动作词用早盘枚举。

## 错误与降级

| 情况 | 行为 |
|------|------|
| 总开关关 | 不调用模块 |
| Live 读仓失败 | 建议段写明失败原因；**不**静默改读 Paper |
| 无持仓 / 无 Key / 超时 / JSON 坏 | 选股照推；建议段降级 |
| `hybrid` 规则异常 | 忽略规则，退化为纯 LLM，打日志 |
| >20 只持仓 | 截断前 20 + 文案注明 |

## UI

- 早盘/尾盘 latest：brief `content` 已含建议段则原样展示；不新做复杂持仓建议 UI。
- Settings：开关 / 模式 / 持仓源。

## 测试

1. 无持仓 → 正文含「无持仓」，选股段仍发送  
2. Mock LLM 合法 JSON → extras + 正文含动作与理由  
3. 非法 action → 回退持有  
4. LLM 抛错 → 降级文案，选股段完整  
5. `enabled=false` → 不调 LLM  
6. `hybrid`：规则候选进入事实包；规则挂掉仍能出建议  
7. 早盘/尾盘挂点各一条集成测试（mock `advise_advice`）

## 实现顺序（概要）

1. 设置字段 + Settings UI  
2. `desk_positions_advice` 核心（load / rules / llm / format / service）  
3. 挂接 closing / morning post_auction  
4. 单测 + 挂点集成测  
5. 文档勾选 / TODO 同步（实现完成后）
