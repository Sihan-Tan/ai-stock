# 黄金坑套件（因子 + 日 K 副图）

> 状态：已实现  
> 日期：2026-08-05

## 目标

将通达信「黄金坑」脚本中**可落地且无未来函数**的买卖类信号，做成综合因子 `GOLDEN_PIT`（黄金坑套件），并在股票详情**日 K**上常驻新增副图；因子页可勾选同一套序列。

## 决策摘要

| 项 | 选择 |
|----|------|
| 接入范围 | 黄金坑 + 井喷等买卖类信号（方案原 B） |
| 未来函数 | 全部剔除；`ZIG` 及依赖不做 |
| 黄金坑波谷 | 无未来近似替代 `TROUGHBARS`（名称保留，算法可与通达信不一致） |
| 副图呈现 | 1～2 条连续曲线 + 信号柱/标记 |
| 因子形态 | 单一综合因子 |
| 日 K 副图 | 常驻（无需开关） |
| 计算真源 | 后端统一计算；日 K 拉 `/api/factors/series`（方案 B） |

## 计算范围（一期）

### 纳入

- **黄金坑**：无未来波谷近似 + `FILTER` 抑制；副图标记/柱 + 文案「黄金坑」
- **井喷**：涨停形态类条件 + 量能 + `COUNT=1`；标记/柱 +「井喷」
- **主曲线**：1～2 条不依赖 ZIG/筹码的强弱/超卖类连续序列
- **输入**：标的日线 OHLCV；可选指数日线（已有 INDEX 映射）；缺失时降级，不阻塞主信号

### 不做

- `ZIG`、「果断买入」、「买/卖」等依赖未来函数的信号
- `WINNER` / `CAPITAL` 等筹码与股本
- AA 全族文字、DMI 全家桶原样复刻（除非某序列被选作主曲线）
- 周 / 月 / 分时副图
- 通达信 1:1 皮肤

## 因子元数据

| 字段 | 值 |
|------|-----|
| `name` | `GOLDEN_PIT` |
| `label` | `黄金坑套件` |
| `category` | `custom`（或 `pattern`） |
| `plot` | `panel` |
| `talib` | `""`（自定义） |
| `default_enabled` | `false`（因子页需勾选；日 K 常驻不依赖勾选） |

`description`：三段式中文说明，并写明黄金坑为无未来近似、与通达信 `TROUGHBARS` 不完全一致。

### 输出列

| 列名 | 含义 |
|------|------|
| `gp_line` | 主连续曲线 |
| `gp_line2` | 可选第二条参考线（一期可省略） |
| `gp_pit` | 黄金坑信号（0 / 非 0） |
| `gp_blowoff` | 井喷信号（0 / 非 0） |

### 接线

- 纯函数模块计算上述列（建议 `packages/indicators/desk_indicators/golden_pit.py` 或 `packages/factor/desk_factor/golden_pit.py`）
- `FactorService.compute_series_from_df` 增加自定义分支（与 price / talib / ml 并列）
- `warmup_calendar_days` 按最大窗口取安全上界（约 80～250 日历日量级）
- 规则策略可引用各输出列，行为同其他 panel 因子

## 日 K 常驻副图

1. `period === "day"` 时，`StockDetailView` 在 bars 就绪后请求：  
   `GET /api/factors/series?symbol=…&names=GOLDEN_PIT&start=…&end=…`
2. 复用现有 series 响应：`series.GOLDEN_PIT.outputs.*`
3. `StockChart` 增加 `priceScaleId: "golden_pit"` pane（仿 MACD 的 scaleMargins 腾位）：
   - 折线：`gp_line`（及可选 `gp_line2`）
   - 信号：`gp_pit` / `gp_blowoff` 非零处置柱或 marker（坑偏红/黄，井喷偏绿）
4. 有该副图时总高度再加一档；失败/空数据不阻断主图与量能/MACD
5. 周 / 月 / 分时不绘制

## 因子页

- 目录展示「黄金坑套件」；勾选后走现有 `FactorCharts` panel 多输出渲染
- 与详情日 K 常驻相互独立

## 架构

| 单元 | 职责 |
|------|------|
| `golden_pit` 计算模块 | OHLCV(+可选指数) → 输出列 |
| `desk_factor` registry + FactorService | 注册元数据；自定义分支算序列 |
| `GET /api/factors/series` | 已有契约，支持 `GOLDEN_PIT` |
| `StockDetailView` + `StockChart` | 日 K 拉数并常驻副图 |
| `FactorCharts` / 因子目录 | 勾选展示同一套输出 |

## 测试

1. 纯函数：给定合成 OHLCV，`gp_pit` / `gp_blowoff` 在构造场景下触发；无未来依赖（信号不因「未来 bar」改写历史点）
2. `get_factor("GOLDEN_PIT")` 字段与 outputs 齐全；`compute_series` 返回各列等长点列
3. 前端：日线请求 names 含 `GOLDEN_PIT`；非日线不请求 / 不画副图（单测或轻量断言）

## 手工验收

- 因子页勾选「黄金坑套件」：副图出现曲线与信号
- 股票详情日 K：量能、MACD 下方可见新副图；切换周/月/分时后该副图消失
- 说明文案可读，含无未来近似提示

## 非目标

- 改策略引擎架构
- 完整通达信脚本逐行移植
- 引入未来函数「仅供对照」模式
