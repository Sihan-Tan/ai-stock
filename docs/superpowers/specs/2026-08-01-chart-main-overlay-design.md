# 标的图主图指标下拉（移动均线族）

> 状态：已实现  
> 日期：2026-08-01

## 目标

在标的详情 K 线工具条上，为**日 / 周 / 月**增加主图指标族下拉；将现有 MA5–MA60 归为「移动均线」。预留「均线战法」扩展位，**首版不下拉展示该项**（待后续公式）。

## 决策摘要

| 项 | 选择 |
|----|------|
| 布局 | C：与周期按钮同一工具条，竖线分隔后接下拉 |
| 可见周期 | 仅 `day` / `week` / `month`；`intraday` 隐藏 |
| 架构 | 方案 1：`mainOverlays` 注册表 + 下拉切族 |
| 首版选项 | 仅「移动均线」（`sma`） |
| 均线战法 | 首版不出现；后续只加注册项 |

## 非目标（首版）

- 「均线战法」具体线条与公式
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

1. 注册表：首版仅 `sma`；day/week/month 可列，intraday 空  
2. `buildLines` 与现有 `buildSmaSeries` 数值一致  
3. `shouldShowMainOverlaySelect(period)`：K 线 true，分时 false  

### 手工验收

- 日 K 默认移动均线，视觉与改前一致  
- 周 / 月有下拉与均线  
- 分时无下拉  
- 无「均线战法」选项  

## 实现顺序（概要）

1. `mainOverlays.ts` + 单测  
2. `StockChart` 按族叠加  
3. `StockDetailView` 工具条下拉与状态  
4. 手工核对日/周/月/分时  
