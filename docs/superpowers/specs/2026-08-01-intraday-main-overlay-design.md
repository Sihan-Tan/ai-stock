# 分时主图指标下拉（分时抄底）

> 状态：已实现  
> 日期：2026-08-01

## 目标

在标的详情**分时**工具条上增加主图指标族下拉；默认「无」保持现有分时展示；提供「分时抄底」（通达信公式移植）作为叠加层。

## 决策摘要

| 项 | 选择 |
|----|------|
| 布局 | 与日 K 相同：周期按钮后竖线 + Dropdown |
| 默认 | **「无」**（`none`）；现有面积线 / 均价线 / 竞价带不变 |
| 首版选项 | 「无」、「分时抄底」（`intraday_dip`） |
| 还原度 | 完整：强弱色带 STICKLINE + 支撑/阻力 + 交叉黄带 + ★/★B 标记 |
| EMA 预热 | 计算用约 **5 个交易日**分钟线；**图表仍只画当天** |
| 架构 | 扩展现有 `mainOverlays` 注册表（方案 1） |

## 非目标

- 不重画「现价」白线（现价 = 现有分时 CLOSE 面积线）
- 不改副图 MACD / 成交量
- 不新增专用后端指标接口
- 不持久化下拉选择（localStorage 可后补）
- 不改日 / 周 / 月现有「移动均线 / 均线战法」行为

## 通达信公式与映射

```text
MA30:=EMA(CLOSE,30);
强弱:EMA(CLOSE,900);
STICKLINE((MA30>强弱),MA30,强弱,1,0),COLOR0000FF;
STICKLINE((MA30<强弱),MA30,强弱,1,0),COLOR00FF00;
H1:=MAX(DYNAINFO(3),DYNAINFO(5));
L1:=MIN(DYNAINFO(3),DYNAINFO(6));
P1:=H1-L1;
阻力:L1+P1*7/8,COLOR00DD00;
支撑:L1+P1*0.5/8,COLOR00DD00;
现价:CLOSE,COLORWHITE,LINETHICK1;          -- 不绘制，沿用现有分时线
STICKLINE(CROSS(支撑,现价),支撑,阻力,1,0),COLORYELLOW;
DRAWTEXT(LONGCROSS(支撑,现价,2),支撑*1.001,'★B'),COLORYELLOW;
DRAWTEXT(LONGCROSS(现价,阻力,2),现价,'★'),COLORRED;
```

| 通达信 | 前端语义 |
|--------|----------|
| `DYNAINFO(3)` | 昨收 `quote.pre_close` |
| `DYNAINFO(5)` | 当日最高（盘中用截至当前分钟的 running high） |
| `DYNAINFO(6)` | 当日最低（running low） |
| `EMA` | α = 2/(N+1)，与现有 `buildEmaSeries` 一致 |
| `CROSS(A,B)` | A 上穿 B（前根 A≤B 且本根 A>B） |
| `LONGCROSS(A,B,2)` | A 上穿 B 后连续至少 2 根保持 A>B（通达信常见语义） |
| `COLOR0000FF` / `00FF00` / `00DD00` / 黄 / 红 | `#0000FF` / `#00FF00` / `#00DD00` / `#EAB308` / `#EF4444`（可微调以暗色可读） |

### 叠加元素

| 元素 | 类型 | 说明 |
|------|------|------|
| MA30 | 线 | EMA30，仅当天点上图 |
| 强弱 | 线 | EMA900（用 5 日预热后裁当天） |
| MA30↔强弱色带 | STICKLINE | 每分钟竖条：红 `MA30>强弱`，绿反之 |
| 阻力 / 支撑 | 线 | 随 running H1/L1 更新的序列（非全日固定水平，贴近盘中 DYNAINFO） |
| 交叉黄带 | STICKLINE | `CROSS(支撑,现价)` 当根：支撑→阻力，黄色 |
| ★B | marker | `LONGCROSS(支撑,现价,2)`，价位≈支撑×1.001，黄 |
| ★ | marker | `LONGCROSS(现价,阻力,2)`，价位≈现价，红 |

## 架构

| 单元 | 职责 |
|------|------|
| `mainOverlays.ts` | 注册 `none`（分时）、`intraday_dip`；扩展产出：`lines` + `sticks` + `markers`；`shouldShowMainOverlaySelect` 含 `intraday` |
| `StockDetailView` | 分时显示下拉；选中 `intraday_dip` 时多拉约 5 日分钟线 + 传入 `preClose`；图例可列关键线末值 |
| `StockChart` | 分时在现有面积/均价之上叠加 sticks / lines / markers；`none` 时零叠加 |
| `format.ts`（或邻域） | 如需：`CROSS` / `LONGCROSS` 纯函数；5 日窗口起算日（跳过周末即可，节假日可后补） |

### 注册表示意

```ts
{ id: "none", label: "无", periods: ["intraday"], build: () => empty }
{ id: "intraday_dip", label: "分时抄底", periods: ["intraday"], build: buildIntradayDip }
// 既有 sma / ma_tactic 不变，periods 仍为 day/week/month
```

### 数据流

1. 分时主图 bars：当天 `09:15–15:00`（现网 `loadBars`）。
2. 指标计算 bars：`from = 约 5 个交易日前 09:15`，`to = 当天 15:00`（仅 `intraday_dip` 时请求）。
3. 在全窗口算 EMA；过滤 `time` 落在当天会话轴的点再 `setData`。
4. H1/L1：当天序列上 running max/min，并与 `pre_close` 取 max/min。

### 状态

- 继续单一 `mainOverlayId`。
- 周期切换时：若当前 id 不在 `listOverlaysForPeriod(period)` 中，回退到该列表首项（分时首项为 `none`，K 线首项为 `sma`）。

## UI

```
[ 分时 ] [ 日 K ] [ 周 K ] [ 月 K ]  |  [ 无 ▾ ]
```

- 分时：下拉可选「无」「分时抄底」
- 日/周/月：仍为「移动均线」「均线战法」（与现网一致）

## 测试

1. `shouldShowMainOverlaySelect("intraday") === true`；`listOverlaysForPeriod("intraday")` 含 `none`、`intraday_dip`
2. 默认分时无叠加系列（面积 + 均价仍在）
3. EMA30/900 数值与 `buildEmaSeries` 一致；5 日预热后当天点与「仅当天」不同（可对 fixture 断言）
4. `CROSS` / `LONGCROSS` 单元测试（边界：刚好 2 根、不足 2 根）
5. 阻力/支撑公式：给定 H1/L1/P1 断言数值

### 手工验收

- 分时默认「无」：与改前视觉一致
- 选「分时抄底」：见强弱色带、支撑/阻力、信号黄带与 ★
- 切换日 K 再回分时：回到「无」（或合理回退），日 K 移动均线不受损

## 风险与备注

- 库内若不足 5 日分钟线，EMA900 仍偏冷启动；live 回退由现有 `/bars/minute` 行为承担。
- 交易日近似：首版按日历减天数并跳过周末；法定节假日未排除可接受。
- lightweight-charts：色带可用 Bar/自定义竖段近似 STICKLINE；标记用 series markers。
