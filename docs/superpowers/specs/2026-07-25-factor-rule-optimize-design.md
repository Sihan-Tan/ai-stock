# 因子一键生成策略 + 完整阈值寻优

**日期：** 2026-07-25  
**状态：** 已实现  
**前置：** 规则策略构建器（`kind: factor_rules`）；ML 因子可进规则（`as_factor`）  
**入口：** 因子页「生成规则策略」；规则构建器 / 回测「阈值寻优」

## 目标

1. **一键生成**：从因子页已勾选的 TA / ML 因子跳到规则构建器，预填可编辑的买卖条件与默认仓位/持仓参数。  
2. **完整寻优**：在选定标的与回测区间上，网格搜索买卖阈值常数、简易仓位（半仓/满仓）、最长持仓天数，将最优结果写回策略 YAML `params` 与条件常数。

## 非目标

- Walk-Forward 内对 ML 重训  
- 多标的联合寻优、组合层仓位  
- 分钟线寻优  
- 自动定时重跑寻优  
- 优化交叉类（`cross_up` / `cross_down`）条件（保留原样，不参与网格）

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 范围档位 | **完整**：阈值 + `position_pct ∈ {50,100}` + `max_hold_bars ∈ {0,5,10,20}` |
| 架构 | 方案 A：一键生成草稿 + 独立寻优 API；回测/执行层读 `params` |
| 一键生成 | 仅打开构建器草稿，**不自动保存** |
| 寻优目标 | 最大化 `total_return`；平局取更小 `max_drawdown` |
| 网格上限 | 约 **200** 组组合；超限或超时明确报错 |
| 可优化条件 | 仅「因子 vs 常数」的比较算子（`gt/gte/lt/lte/eq` 等）；交叉 / near_pct 等保留 |

## 一、一键生成策略

### 入口与路由

- 因子页「因子图表」：勾选 ≥1 个因子时启用按钮「生成规则策略」  
- 跳转：`/strategies/new/rules?from=factors&factors=<urlencoded 逗号分隔名>`  
- 规则构建器读取 query，加载因子目录后预填 `RuleDoc`

### 预填规则

| 因子类型 | 买条件（默认） | 卖条件（默认） |
| --- | --- | --- |
| `ml:*` | `factor gt 0.6` | `factor lt 0.4` |
| 振荡类（名含 `RSI` / `CCI` / `WILLR` 等，实现时用小白名单） | `factor lt 30` | `factor gt 70` |
| 其它 TA | `factor cross_up SMA_20`（若自身已是均线类则 `CLOSE cross_up factor`） | 对应 `cross_down` |

- 多因子：`buy.combine = all`（每因子一条）；`sell.combine = any`  
- 默认顶层：

```yaml
params:
  position_pct: 100   # 单笔目标仓位占可用资金百分比；100≈满仓口径
  max_hold_bars: 0    # 0=不限制持仓交易日数
```

- `id` / `name`：由首因子名派生可编辑草稿名（如 `rule_from_RSI_14`）

### 错误

- 未勾选因子：按钮 disabled 或提示  
- 未知因子名：跳过并 toast/日志列出跳过项；若全部无效则空模板

## 二、完整寻优

### API（草案）

`POST /api/strategies/optimize-rules`

```json
{
  "symbol": "600519.SH",
  "start": "2024-01-01",
  "end": "2025-12-31",
  "yaml_body": { "...factor_rules doc..." },
  "buy_grid": [0.5, 0.55, 0.6, 0.65, 0.7],
  "sell_grid": [0.3, 0.35, 0.4, 0.45, 0.5],
  "position_pcts": [50, 100],
  "max_hold_bars_list": [0, 5, 10, 20]
}
```

- 未传 grid 时：对检测到的 ML 常数比较用上表默认；若无任何可优化常数比较，返回明确错误「无可优化阈值条件」  
- 组合数 = `|buy| × |sell| × |pos| × |hold|`（若买卖各有多条可优化常数，采用「同侧共用一个网格值」简化：买侧所有买阈值常数同步替换为同一 `buy_v`，卖侧同理）  
- 超过 200：`400` + 文案建议缩小网格  

### 执行

1. 解析 YAML，找出买/卖侧「因子 vs 常数」条件  
2. 对每组参数：改写常数与 `params` → 调用现有回测引擎（单标的、日线）  
3. 收集 `total_return` / `max_drawdown`（与现网回测报告字段对齐）  
4. 返回：

```json
{
  "best": {
    "yaml_body": {},
    "metrics": { "total_return": 0.12, "max_drawdown": -0.08, "trades": 20 },
    "buy_threshold": 0.6,
    "sell_threshold": 0.4,
    "position_pct": 100,
    "max_hold_bars": 10
  },
  "tried": 80,
  "skipped": 0
}
```

### UI

- 规则构建器工具栏：「阈值寻优」→ 弹层填标的/区间（可复用 `DateRangePresetSelect`）→ 调用 API → 用 `best.yaml_body` 覆盖编辑器并展示指标  
- 可选：回测页对当前 `factor_rules` 策略提供同入口（同一 API）

## 三、执行层：`params` 生效

### Schema

`kind: factor_rules` 文档可选：

```yaml
params:
  position_pct: 100    # (0, 100]
  max_hold_bars: 0     # 整数；0=关闭
```

### 回测

- Sizer：读取策略 `params.position_pct`（缺省保持现网约 95% 行为或统一为 100，实现计划锁定一种并单测）  
- 持仓：记录开仓 bar 序号；当 `max_hold_bars > 0` 且持仓天数 ≥ 该值时，当日发出卖信号（与规则卖信号 OR；卖优先仍成立）

### 纸交易 Runner

- 下单数量口径尽量对齐 `position_pct`（受风控单笔上限约束）  
- `max_hold_bars`：用持仓开仓日与当前 asof 的交易日差强制平仓信号（实现计划写清数据来源）

## 四、组件边界

| 单元 | 职责 |
| --- | --- |
| `Factors.tsx` | 勾选校验 + 跳转 query |
| `StrategyRuleBuilder` | 解析 query 预填；寻优弹层；应用 best YAML |
| `desk_strategy` / YAML | `params` 解析 |
| `desk_backtest` | sizer + max hold |
| `desk_broker.paper_runner` | 仓位/持仓对齐（能通则做，否则回测优先、Runner 降级说明） |
| `POST .../optimize-rules` | 网格编排 + 调回测 |
| 单测 | 预填映射、网格截断、最优选择、max_hold 强制平仓、position_pct 影响仓位 |

## 五、验收

1. 因子页勾选 ML + RSI → 生成规则页可见预填条件与默认 params  
2. 寻优在小网格上返回 best，编辑器常数与 params 被更新  
3. `max_hold_bars=5` 的回测会出现因到期产生的卖出  
4. `position_pct=50` 与 `100` 在同条件回测中仓位/收益可区分（单测或报告字段）  
5. 组合数 >200 时 API 拒绝且前端可读错误  
6. 无「因子 vs 常数」条件时寻优失败提示清晰  

## 开放实现细节（计划阶段写死）

- 振荡类因子白名单完整列表  
- 回测缺省 `position_pct`：95 vs 100  
- 纸交易 Runner 对 `max_hold_bars` 若数据不足时的降级策略  
- 寻优是否同步阻塞 HTTP（首版同步 + 前端 busy；超时建议 ≤60s）
