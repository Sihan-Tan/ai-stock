# 尾盘选股（镜像晨会 + 策略引擎扫股）

**日期：** 2026-07-25  
**状态：** 已实现  
**入口：** 导航「尾盘选股」；定时 job `run_closing_pick`；策略 `params.roles` 含 `closing`

## 目标

收盘前（默认约 14:40）用已标记为「尾盘」的策略，在**系统证券宇宙**上只评买入条件，产出次日预埋候选清单：落库、飞书推送、页面可重跑/看历史、一键进自选。**不下单**。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 目的 | 次日预埋（隔夜 / 次日竞价博弈），非当日尾盘博弈复盘清单 |
| 规则 | 复用策略引擎（YAML / `factor_rules` 等）；不新建 DSL |
| 触发 | 定时默认跑 + 页面手动重跑 / 历史 / bind |
| 策略范围 | 多策略；`params_json.roles` 含 `"closing"`；页面可勾选子集 |
| 架构 | 方案 A：独立包 `closing_pick`，镜像晨会，不挂纸交易 Runner |
| 宇宙 | `SecurityMeta` 在市标的（`is_delisted=false` / listed） |
| 打分 | 有 buy 信号即入选；`score` 可用当日涨跌幅等简单启发式，缺省 `1.0` |
| 多策略同票 | `closing_picks` **按策略分行**；前端可按票聚合展示 |
| 不做（首版） | 自动开仓、隔夜持仓管理、全市场性能优化（并发/缓存可后补）、卖点扫描 |

## 边界

**做什么**

- `ClosingPickService.run`：交易日校验 → 解析尾盘策略列表 → 扫宇宙 → 评 buy → 写 brief/picks → 飞书
- API / 前端 / 定时 / bind 自选，对标晨会体验
- 策略 UI：勾选「用于尾盘选股」读写 `roles`

**不做什么**

- 不改纸交易 / 实盘下单循环
- 不改晨会竞价打分逻辑
- 不强制策略必须是 `factor_rules`（能产出 buy 信号的 YAML/注册策略均可；首版优先打通 `factor_rules` + 已有 `_yaml_on_bar` 路径）

## 数据模型

### `closing_briefs`

| 列 | 说明 |
| --- | --- |
| `asof` | 交易日 |
| `stage` | 首版固定 `closing` |
| `content` | 推送/展示文案 |
| `extras_json` | 策略数、命中数、strategy_ids 等 |
| `created_at` | 写入时间 |

### `closing_picks`

| 列 | 说明 |
| --- | --- |
| `asof` | 交易日 |
| `strategy_id` | 命中策略 |
| `pick_type` | 首版 `stock` |
| `code` / `name` | 标的 |
| `score` | 启发式分数 |
| `meta_json` | 信号摘要、涨跌幅等 |

同日重跑：先删该 `asof`（若指定了 `strategy_ids` 则只删对应策略行）再写入，避免脏数据。

### 策略打标

```json
{
  "roles": ["closing"]
}
```

存在 `strategies.params_json`；与其它 params 合并，不覆盖无关键。无 `roles` 或未含 `closing` → 不参与定时；页面「可标记列表」仍可展示全部非 archived 策略供勾选写入。

## 扫描与求值

1. **宇宙**：`SecurityMeta` 未退市 symbol 列表。
2. **K 线**：按策略 timeframe（默认日线）取足够历史；无数据则跳过该标的。
3. **求值**：对最新 bar 只关心 **buy** 侧是否产生信号（复用 `StrategyRegistry` / `eval_factor_rules` / `_yaml_on_bar` 已有能力；实现时抽「单标的单策略 dry 信号」辅助函数，避免下单）。
4. **摘要文案**：日期、参与策略数、命中只数、前若干 `symbol(strategy)`。

性能：全宇宙 × 多策略可能较慢；首版同步跑完即可，超时/进度条不作为硬门禁；后续可加限制或并发。

## API（`/api/closing`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/run` | body: `asof?`, `strategy_ids?[]`；空 ids → 全部带 `closing` 的 |
| `GET` | `/latest` | 当日 brief + picks（可按 strategy 分组） |
| `GET` | `/history` | query `asof`；指定日结果 |
| `POST` | `/bind` | 命中个股进自选；`asof?`, `limit?`, `strategy_ids?`, `symbols?` |
| `GET` | `/strategies` | 列出策略及是否已标 `closing`（供勾选） |

策略侧：既有策略更新接口支持 patch `params.roles`；或尾盘页调用专用/通用 update。

## 定时与 Job

- Job id / 方法：`run_closing_pick`
- 默认 cron：约 **14:40** 工作日（与现有 `jobs` 配置同风格，可改）
- 非交易日：写跳过文案或直接 return，与晨会一致
- `MarketJobs` + `scheduler._add` 注册；行情同步页任务名映射「尾盘选股」

## 前端

- 路由 `/closing`，导航「尾盘选股」
- 布局对标 `Morning.tsx`：日期 Chip、文案、个股表、刷新 / 立即跑 / 进自选
- 额外：多选本次策略（`GET /strategies`）
- 策略列表或编辑：Checkbox「用于尾盘选股」

## 飞书

- `FeishuWebhookChannel.send`，标题「尾盘选股」
- `category=closing`，`dedupe_key=closing:{asof}`
- 正文用 brief `content`

## 包与文件（预期）

- `packages/closing_pick/desk_closing_pick/`（`ClosingPickService`、`bind.py`）
- `apps/api/app/routes/closing.py`
- ORM + alembic（或启动补表，与项目现有习惯一致）
- `apps/web/src/pages/Closing.tsx` + nav / App 路由
- 单测：打标过滤、空宇宙、命中写入、bind、非交易日

## 成功标准

1. 至少一只策略标 `closing` 后，`POST /run` 在有行情数据时可产生 picks 或明确「0 命中」文案
2. 定时 job 可注册；手动跑与定时共用同一 Service
3. 页面可展示结果并 bind 进自选
4. 飞书在已配置 webhook 时收到一条（去重同日）
5. 不产生任何 paper/live 订单

## 开放实现细节（计划阶段定）

- 日线「当日未收盘」bar：用当日已有 OHLCV 快照还是上一交易日收盘 bar——实现时与现有 bar 加载约定对齐，并在计划中写死一种
- Python 注册策略 vs 仅 YAML：首版以 YAML/`factor_rules` 为主；python 策略若无统一 on_bar 上下文可标为后续
