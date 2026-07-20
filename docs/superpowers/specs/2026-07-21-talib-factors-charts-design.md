# TA-Lib 因子目录与主/副图展示

## 背景

因子页（`Factors.tsx`）目前几乎是 JSON 占位；`FactorService.list_factors` 仅少量占位项；`desk_indicators.compute` 已支持 SMA/EMA/RSI/MACD/ATR/BOLL（优先 TA-Lib）。需要把 TA-Lib 类技术因子做成可勾选目录，并在同一页用图表展示。

## 目标

- 提供可配置的因子注册表（尽量多挂常用 TA-Lib，可开关）。
- 一期默认启用约 15–20 个常用因子，其余注册但默认不勾选。
- 因子页左右结构：左目录勾选，右主图（价格 + overlay）+ 下方 panel 副图。
- 统一 `GET /api/factors` 与 `GET /api/factors/series`，基于本地 `bars_daily` 计算。

## 非目标

- 一期不做页面上自定义参数（period 等）覆盖；一律用注册表默认 params。
- 一期不强制挂载 TA-Lib 全部函数；先挂 overlap / momentum / volatility / volume 常用子集，全量挂载为二期。
- 不做分钟线因子；不做回测/选股打分联动。
- 不做前端 E2E；以 API / Registry 单测为主。
- 不改情绪、投研、交易相关模块。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 因子范围 | 尽量多挂可开关；一期默认约 16 个常用 |
| 图表布局 | 主图 + 下方多面板副图 |
| 技术方案 | 注册表 + 统一计算 API + 因子页主/副图 |
| 页面结构 | 左目录 / 右图表（不另开整页顶部「已选」区打断左右结构） |
| 目录交互 | 已勾选在左栏常显；未勾选按分类默认折叠 |
| 图表库 | 复用 `lightweight-charts`（与个股图一致） |
| 参数 | 一期仅注册表默认 params |

## 架构

```
Factors.tsx
  ├─ GET /api/factors          → FactorRegistry 元数据
  └─ GET /api/factors/series   → bars_daily + desk_indicators
        ├─ FactorRegistry（name / category / params / plot / default_enabled）
        ├─ desk_indicators（TA-Lib 优先，纯 Python 降级）
        └─ bars_daily（OHLCV）
```

### 后端

- **FactorRegistry**（建议落在 `packages/factor` 或 `packages/indicators`，由 `FactorService` 暴露）
  - 字段：`name`、`label`、`category`、`params`、`outputs`、`plot`（`overlay` | `panel`）、`default_enabled`、`enabled`（是否出现在目录；一期默认 true）
  - `list()`：返回目录；`compute_series(symbol, names, start, end)`：取 bars 并按 name 批量计算

- **扩展 `desk_indicators`**
  - 在现有 SMA/EMA/RSI/MACD/ATR/BOLL 基础上，按注册表补齐一期默认名单及已注册但默认关的常用项（如 KD/STOCH、CCI、ADX、OBV、MOM 等）
  - 未知 name：调用方返回 400，不静默跳过全部请求（可部分成功策略：未知名列入 `errors[]`，已知名仍返回——一期采用「任一未知 name → 整请求 400」，实现更简单）

- **路由**（扩展现有 `apps/api/app/routes/factor_ml.py`）
  - 保留/对齐 `GET /api/factors`
  - 新增 `GET /api/factors/series`

### 前端

- 重做 `apps/web/src/pages/Factors.tsx`
  - 左：搜索 + 按 `category` 分组；已勾选项常显；未勾选分类折叠
  - 右：标的（复用个股搜索能力）、区间（近 3M / 1Y / 自定义）、主图 + 副图
  - 勾选变化可 debounce 后重拉 series；副图数量建议上限约 6，超出提示精简勾选
  - overlay 只叠主图；每个 panel 因子一块副图；多输出（如 MACD）同 panel 多线/柱
  - 主图与副图共用时间轴、十字线联动

## API

### `GET /api/factors`

响应：

```json
{
  "factors": [
    {
      "name": "SMA_20",
      "label": "SMA 20",
      "category": "trend",
      "params": { "period": 20 },
      "outputs": ["sma_20"],
      "plot": "overlay",
      "default_enabled": true,
      "enabled": true
    }
  ]
}
```

### `GET /api/factors/series`

查询参数：`symbol`（必填）、`names`（逗号分隔，必填）、`start`、`end`（可选，缺省由前端区间约定，如近 1 年）。

成功响应（示意）：

```json
{
  "symbol": "600519.SH",
  "engine": "talib",
  "bars": [{ "date": "2025-01-02", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1 }],
  "series": {
    "SMA_20": { "outputs": { "sma_20": [{ "date": "2025-01-02", "v": 1.0 }] } },
    "MACD": {
      "outputs": {
        "macd": [{ "date": "...", "v": 0.1 }],
        "signal": [{ "date": "...", "v": 0.05 }],
        "hist": [{ "date": "...", "v": 0.05 }]
      }
    }
  }
}
```

`engine`：`talib` | `python`。规则：本次计算凡有任一指标走纯 Python 降级，则标 `python`，否则 `talib`。

## 一期默认启用名单

**overlay：** `SMA_5`、`SMA_20`、`SMA_60`、`EMA_12`、`EMA_26`、`BOLL`  

**panel：** `RSI_14`、`MACD`、`ATR_14`、`STOCH`（展示名可用「KD」）、`CCI_14`、`ADX_14`、`OBV`、`MOM_10`

其余已注册项：`default_enabled=false`，出现在对应分类折叠区内。

## 目录交互（左栏）

- 保持左右布局；已选不抽到整页顶栏。
- 已勾选：左栏上部「已选」小节始终列出（仍在左侧，不破坏左右结构）。
- 未勾选：下方按分类默认折叠，展开后再勾选。
- 初始勾选 = 各因子 `default_enabled`。

## 错误处理

| 情况 | 行为 |
| --- | --- |
| 无本地 `bars_daily` | 4xx + 明确文案「无本地日线」；前端展示提示，不画空图 |
| `names` 含未知因子 | 400 |
| 缺少 TA-Lib | 纯 Python 降级；响应 `engine` 标明 |
| 副图勾选过多 | 前端提示精简（约 6）；不强制后端限流 |

## 测试

- Registry：默认启用名单与 `plot`/`category` 断言。
- series：固定 OHLCV fixture，对 SMA_20 / RSI_14 等关键末值或非空长度断言。
- 未知 name、空 bars 的 API 错误路径。

## 实现落点（参考）

| 区域 | 路径 |
| --- | --- |
| 因子页 | `apps/web/src/pages/Factors.tsx` |
| 因子 API | `apps/api/app/routes/factor_ml.py` |
| FactorService | `packages/factor/desk_factor/` |
| 指标 | `packages/indicators/desk_indicators/` |
| 图表参考 | `apps/web/src/stock/StockChart.tsx` |

## 验收标准

1. `/factors` 左目录可勾选，已勾常显、未勾分类折叠；右为标的 + 主/副图。
2. 默认勾选覆盖一期名单；取消/勾选后图表随之更新。
3. `GET /api/factors` 与 `GET /api/factors/series` 可用；无日线时有明确错误提示。
4. 有 Registry / series 基础单测。
