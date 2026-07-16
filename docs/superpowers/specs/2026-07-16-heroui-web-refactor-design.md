# HeroUI Web 全量重构设计

日期：2026-07-16  
状态：已确认（待实现计划）

## 背景与目标

刻度 Desk 前端（`apps/web`）目前为手写 CSS + 单体 `App.tsx` 页面。目标：

1. 用 **HeroUI v3** 重构全部展示页与壳层。
2. 默认视觉延续现有 **Desk 品牌深色**（青绿底 + 铜色强调）。
3. 支持一键切换到 **浅色交易台**主题，刷新后保留。
4. 之后新增页面一律使用 HeroUI 组件 / Tailwind 样式，不再扩展旧 `.btn` / `.card` 体系。

## 已确认决策

| 项 | 选择 |
|----|------|
| 范围 | 全量：壳层 + 现有全部路由页 |
| 默认主题 | A · Desk 品牌深色 |
| 可选主题 | C · 浅色交易台（可切换） |
| 布局 | A · 左侧栏；主题切换在侧栏底部 |
| 技术路线 | HeroUI v3 + Tailwind CSS v4；必要时升级 React 19 |

## 非目标

- 不新增业务功能、不改后端 API 契约。
- 不强制移动端汉堡菜单（窄屏允许侧栏纵向堆叠即可）。
- 不迁移到 Next.js；保持 Vite SPA + React Router。

## 技术栈

- Vite + React 19（若 HeroUI v3 要求；从 React 18 升级）
- `react-router-dom`（已有 BrowserHistory 路由，path 不变）
- `@heroui/react` + `@heroui/styles`
- Tailwind CSS v4（`@import "tailwindcss"` + `@import "@heroui/styles"`）
- 主题：`html[data-theme="desk-dark"|"desk-light"]` + CSS 变量；偏好存 `localStorage` key `desk-theme`

## 应用结构

```
apps/web/src/
  main.tsx              # BrowserRouter + 主题初始化
  App.tsx               # 路由表 + 挂载 AppShell
  api.ts                # 保留
  styles.css            # Tailwind + HeroUI + 主题变量（删除旧手写组件样式）
  theme/                # 主题读写与 applyTheme 辅助
  layout/AppShell.tsx   # 左侧栏、标题、健康区、主题切换
  pages/
    MarketSync.tsx      # 已有，改为 HeroUI
    Overview.tsx
    Watchlist.tsx
    Sentiment.tsx
    Lhb.tsx
    Calendar.tsx
    Strategies.tsx
    Factors.tsx
    Paper.tsx
    Risk.tsx
    Alerts.tsx
    Research.tsx
    Morning.tsx
    Review.tsx
    Knowledge.tsx
```

路由 path 保持不变：`/`、`/market-sync`、`/watchlist`、…、`/knowledge`。

## 组件映射

| 现有 | HeroUI / 约定 |
|------|----------------|
| `.card` | `Card` / `CardHeader` / `CardBody` |
| `.btn` / `.primary` | `Button`（`variant` / `color`） |
| `<table>` | `Table`（含空态） |
| `.banner.warn` | `Alert` |
| 健康 JSON 条 | `Chip` + 简短状态；详情可折叠 |
| `pre` JSON | `Code` + `ScrollShadow` |
| `input` / `textarea` | `Input` / `Textarea` |
| loading | `Spinner` |
| 侧栏 NavLink | `Listbox` 或 `Button as={NavLink}` |

业务逻辑（`api` 调用、Job 轮询、按钮动作）保持不变，只换 UI。

## 主题 Token

### desk-dark（默认）

- `--ink` `#07151c`
- `--panel` `#0d222c`
- `--line` `#1e4554`
- `--mist` `#8aa9b5`
- `--text` `#e7f1f4`
- 强调铜 `#d4a574`；信号绿 `#3ecf9a`

### desk-light

- 页面底 `#f4f6f8`；卡片白
- 字色深灰；强调青绿 `#0f766e`

语义映射：`primary` 跟主题强调色；`warning` / `danger` / `success` 两套各定义一组，保证深浅下对比度可读。

首屏尽量在 React 渲染前读取 `localStorage` 并设置 `data-theme`，避免闪白/闪黑。

## 验收标准

1. `apps/web` 下 `npm run build` 通过。
2. 全部现有路由可进入；刷新留在当前 URL。
3. 深/浅主题切换即时生效，刷新后保持。
4. `/health` 中 `db: false` 时壳层显示 `Alert`（API 不可达另有错误提示）。
5. 行情同步页：手动触发与任务表轮询行为与重构前一致。
6. 主样式不再依赖旧 `.btn` / `.card`；过时规则从 `styles.css` 移除。

## 风险与对策

| 风险 | 对策 |
|------|------|
| React 19 / Tailwind v4 升级摩擦 | 严格按 HeroUI 官方 Vite 文档；先打通壳层再迁页面 |
| HeroUI v3 API 与示例不一致 | 以已安装包的类型与官方文档为准做适配 |
| 巨型 `App.tsx` 拆分易漏路由 | 拆页后用路由表单测或手工清单核对全部 path |

## 实现顺序（概要）

1. 依赖与 Tailwind / HeroUI 接入；主题变量与切换。
2. `AppShell` + 路由外壳。
3. 按页迁移（优先 MarketSync / Overview / Watchlist，其余同等完成因范围已定为全量）。
4. 删除旧样式；build 与手工验收。

详细步骤在用户批准本 spec 后写入 implementation plan。
