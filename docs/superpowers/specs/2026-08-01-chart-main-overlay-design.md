# 标的图主图指标下拉（移动均线族）

> 状态：已实现（含均线战法）  
> 日期：2026-08-01

## 目标

在标的详情 K 线工具条上，为**日 / 周 / 月**增加主图指标族下拉；将现有 MA5–MA60 归为「移动均线」；「均线战法」为通达信公式移植（布林轨 + EMA）。

## 决策摘要

| 项 | 选择 |
|----|------|
| 布局 | C：与周期按钮同一工具条，竖线分隔后接下拉 |
| 可见周期 | 仅 `day` / `week` / `month`；`intraday` 隐藏 |
| 架构 | 方案 1：`mainOverlays` 注册表 + 下拉切族 |
| 选项 | 「移动均线」（`sma`）、「均线战法」（`ma_tactic`） |

### 均线战法（X_1=1）

| 线 | 公式 | 颜色 / 线宽 |
|----|------|-------------|
| 上轨 | MA(C,60)+2*STD(C,60) | cyan `#22d3ee` |
| 上上轨 | MA(C,90)+2*STD(C,90) | `#c080ff` |
| 生命线 | EMA(C,144) | green |
| 下下轨 | MA(C,90)-2*STD(C,90) | `#c080ff` |
| 下轨 | MA(C,60)-2*STD(C,60) | cyan |
| 红 | EMA(C,7) | red，线宽 3 |
| 绿 | EMA(C,20) | green，线宽 2 |

STD 采用通达信总体标准差（除以 N）；EMA 采用 α=2/(N+1)。

## 非目标

- 副图（MACD / 成交量）切换
- 新后端接口（前端用已有 OHLCV 计算）
- localStorage 记忆（可后补）

## 架构

| 单元 | 职责 |
|------|------|
| `apps/web/src/stock/mainOverlays.ts` | 注册表：`id`、`label`、适用 `periods`、`buildLines(bars)` |
| `StockDetailView` | 工具条下拉；`mainOverlayId` 状态；分时隐藏 |
| `StockChart` | 接收当前族线条（或 `mainOverlayId`），主图叠加，不再写死「仅 day 画 MA」 |

### 扩展约定

新增「均线战法」时：

1. 在 `mainOverlays` 注册 `{ id: "ma_tactic", label: "均线战法", periods, buildLines }`
2. 下拉自动多出选项
3. 不改工具条结构

## UI

```
[ 分时 ] [ 日 K ] [ 周 K ] [ 月 K ]  |  [ 移动均线 ▾ ]
```

- 分时选中：隐藏分隔线 + 下拉
- 默认 `mainOverlayId = "sma"`
- 日↔周↔月切换保留当前族；分时往返后恢复

## 移动均线行为

- 周期与颜色：沿用 `DAILY_MA_LINES`（MA5/10/20/30/60）及现有图例
- **日 / 周 / 月**：均对**当前周期** bars 计算 SMA（周 K 的 MA5 = 5 根周线）
- bars 不足某档时跳过该线，与现网一致
- 副图 MACD/成交量逻辑不变

## 测试

1. 注册表含 `sma` + `ma_tactic`；day/week/month 可列，intraday 空  
2. `sma.buildLines` 与现有 `buildSmaSeries` 数值一致  
3. `ma_tactic`：上轨 = MA60+2*STD60；红/绿线宽 3/2  
4. `shouldShowMainOverlaySelect(period)`：K 线 true，分时 false  

### 手工验收

- 日 K 默认移动均线；可切换「均线战法」见 7 条线  
- 周 / 月同样可切换  
- 分时无下拉  

