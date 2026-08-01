# 分时副图「资金趋势」（通达信公式移植）

> 状态：待实现  
> 日期：2026-08-01

## 目标

在标的详情**分时**图上增加一块常驻副图「资金趋势」，移植通达信公式（主力进/撤、大盘资金进/撤、趋势线及准备/买入/逃顶等信号）。完整还原；不替换现有成交量与 MACD。

## 决策摘要

| 项 | 选择 |
|----|------|
| 可见周期 | 仅 `intraday` |
| 出现方式 | 默认常驻（非下拉切换） |
| 布局 | 主图 → 成交量 → MACD → **资金趋势** |
| INDEX 源 | 按市场：`*.SH` → `000001.SH`；`*.SZ` → `399001.SZ` |
| 还原度 | 完整：柱 + 趋势线 + STICKLINE + DRAWTEXT |
| 预热 | 个股与指数均约 5 个交易日分钟线；图上只画当天 |
| 会话日 | 与分时主图一致：`sessionDateFromBars`（非交易日回退） |

## 非目标

- 日 / 周 / 月副图
- 副图指标下拉切换
- 新后端专用指标接口（沿用 `/api/market/bars/minute`）
- 改主图「分时抄底」或强弱色带开关语义
- 持久化 pane 高度

## 通达信公式要点（T=1）

```text
T:=1;
V1:=(C*2+H+L)/4*10;
V2:=EMA(V1,13)-EMA(V1,34);
V3:=EMA(V2,5);
V4:=2*(V2-V3)*5.5;
主力撤: IF(V4<=0,V4,0), COLORBLUE;
主力进: IF(V4>=0,V4,0), COLORFF00FF;

-- INDEX* 为大盘指数 OHLC
V8:=(INDEXC*2+INDEXH+INDEXL)/4;
V9:=EMA(V8,13)-EMA(V8,34);
VA:=EMA(V9,3);
VB:=(V9-VA)/2;
大盘资金进场: IF(VB>=0,VB,0), COLORRED;
大盘资金撤走: IF(VB<=0,VB,0), COLORGREEN;

V11:=3*SMA((C-LLV(L,55))/(HHV(H,55)-LLV(L,55))*100,5,1)
    -2*SMA(SMA((C-LLV(L,55))/(HHV(H,55)-LLV(L,55))*100,5,1),3,1);
趋势线: EMA(V11,3);
V12:=(趋势线-REF(趋势线,1))/REF(趋势线,1)*100;

准备现金 / 买入股票 / 卖临界 / 见顶清仓 等 STICKLINE + DRAWTEXT + FILTER
以及「大盘/主力 × 趋势线阈值」条件加强柱
```

说明：

- 原式中 `V5`/`V6`/`V7` 未参与最终绘制，**可不实现**（YAGNI）。
- `SMA(X,N,1)`：通达信递推 `Y = (X+(N-1)*Y')/N`（M=1）。
- `FILTER(cond,N)`：条件成立后 N 根内不再触发。
- `HHV`/`LLV`/`REF`/`EMA`：与现有 `format` / 通达信语义一致；EMA α=2/(N+1)。

### 绘制元素

| 元素 | 类型 | 颜色 |
|------|------|------|
| 主力进 | 柱（≥0） | `#FF00FF` |
| 主力撤 | 柱（≤0） | `#0000FF` |
| 大盘资金进场 | 柱（≥0） | `#EF4444` / 红 |
| 大盘资金撤走 | 柱（≤0） | `#22C55E` / 绿 |
| 趋势线 | 线 | 可读亮色（如 `#F8FAFC`） |
| 准备现金 | 竖条 0→8 + 文「准备」 | `#CC9900` |
| 买入股票 | 竖条 0→16 + 文「买入」 | 柱 `#0099FF`，字黄 |
| 卖临界 | 竖条 100→95 | `#FFFF00` |
| 逃顶 | 文「逃顶」@90 | 黄 |
| 条件加强柱 | 0→30 / 0→40 | 红/绿/品红/蓝 |

副图独立 price scale（建议约 0–100 量纲以容纳趋势线与信号柱；主力/大盘柱可同轴或按实现择一，优先保证趋势线与信号可读）。

## 架构

| 单元 | 职责 |
|------|------|
| `apps/web/src/stock/indexSymbol.ts` | `resolveIndexSymbol(stockSymbol)` → 000001.SH / 399001.SZ |
| `apps/web/src/stock/tdxMath.ts`（或并入现有） | `smaTdx`、`hhv`/`llv`、`filterSignal`、`ref` |
| `apps/web/src/stock/intradayFundFlow.ts` | 纯函数：对齐个股+指数 → 产出 lines / histograms / sticks / markers |
| `StockDetailView` | 分时拉指数分钟（同会话日 + 5 日预热）；传入 `StockChart` |
| `StockChart` | `addFundFlowPane`；调整主图/量/MACD 的 `scaleMargins` 与容器高度，为第四区腾位 |

### 数据流

1. 个股分时 bars：现网（含非交易日回退）。
2. `sessionDate = sessionDateFromBars(stockBars)`。
3. 指数：`loadMinuteBarsRange(indexSymbol, shiftTradingDaysBack(sessionDate,5), sessionDate)`。
4. 按 `ts` 排序，EMA/HHV 在全窗口计算，映射到当天会话轴后 `setData`。
5. 指数与个股按北京分钟对齐；无指数 bar 的分钟：大盘相关序列该点跳过或置空（不画）。

### 高度与边距

现网分时在 `showMacd` 时高度约 400px、主图 `bottom≈0.46`。增加资金趋势后：

- 容器高度适当加大（如 compact 360 / 常规 480，实现时可微调）。
- 重新分配 volume / macd / fund 三档 `scaleMargins`，避免重叠；主图仍占上半。

## UI

- 无新下拉；副图无标题芯片也可（可选右侧极简图例：趋势线色点）。
- 十字光标：副图不抢主图价格浮层；可不做副图专用 hover。

## 测试

1. `resolveIndexSymbol("600519.SH") === "000001.SH"`；`"000001.SZ" === "399001.SZ"`；创业板 `300xxx.SZ` → 深成指。
2. `smaTdx` / `filterSignal` 小序列黄金值。
3. `buildIntradayFundFlow`：给定固定 OHLC fixture，断言趋势线末值有限、主力进/撤符号与 V4 一致。
4. 缺指数 bars 时不抛错，个股侧主力/趋势仍可产出。

### 手工验收

- 分时可见四层：主图、量、MACD、资金趋势。
- 沪/深标的分别请求对应指数分钟（网络面板）。
- 日 K 无该副图。
- 非交易日回退会话日时，副图与主图同一天。

## 风险

- 四 pane 拥挤：靠调 margins/高度缓解。
- 指数分钟缺失导致大盘柱空白：可接受；日志级可选。
- 公式中部分 STICKLINE 宽度（通达信 `width=5/10/15`）用 Bar 近似，不必像素级一致。
