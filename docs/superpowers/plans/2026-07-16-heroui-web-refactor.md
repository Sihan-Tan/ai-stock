# HeroUI Web Full Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `apps/web` 全量改为 HeroUI v3 + Tailwind v4，默认 Desk 深色主题并可切换浅色，左侧栏壳层，路由与业务逻辑不变。

**Architecture:** 先接入 Tailwind/HeroUI 与主题系统，再抽 `AppShell`，最后把 `App.tsx` 内各页拆到 `pages/*` 并用 HeroUI 组件替换手写 UI。主题通过 `html[data-theme]` + CSS 变量驱动。

**Tech Stack:** Vite、React 19、react-router-dom、@heroui/react、@heroui/styles、Tailwind CSS v4、vitest（主题纯函数单测）

**Spec:** `docs/superpowers/specs/2026-07-16-heroui-web-refactor-design.md`

---

## File map

| Path | Responsibility |
|------|----------------|
| `apps/web/package.json` | 依赖与 scripts（含 `test`） |
| `apps/web/vite.config.ts` | Vite + Tailwind v4 插件 |
| `apps/web/src/styles.css` | Tailwind / HeroUI import + 主题变量 |
| `apps/web/src/theme/theme.ts` | `ThemeId`、读写 localStorage、`applyTheme` |
| `apps/web/src/theme/theme.test.ts` | 主题单测 |
| `apps/web/src/theme/bootTheme.ts` | 首屏防闪：在 React 前 apply |
| `apps/web/index.html` | 内联极短 boot 脚本或由 `bootTheme` 从 main 最早调用 |
| `apps/web/src/main.tsx` | bootTheme + BrowserRouter + App |
| `apps/web/src/layout/AppShell.tsx` | 侧栏、标题、健康 Alert/Chip、主题切换 |
| `apps/web/src/layout/nav.ts` | `NAV` 常量 |
| `apps/web/src/App.tsx` | 仅 Routes + AppShell |
| `apps/web/src/pages/*.tsx` | 各业务页（HeroUI） |
| `apps/web/src/api.ts` | 不变 |
| `apps/web/src/types.ts`（可选） | `SetLog` 等共享类型 |

---

### Task 1: 升级依赖并接入 Tailwind v4 + HeroUI v3

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/vite.config.ts`
- Modify: `apps/web/src/styles.css`（先换成最小可编译样式）
- Modify: `apps/web/tsconfig.json`（若 React 19 types 需要）

- [ ] **Step 1: 安装依赖**

在 `apps/web` 执行：

```bash
cd apps/web
npm install react@19 react-dom@19 @heroui/react @heroui/styles
npm install -D tailwindcss @tailwindcss/vite @types/react@19 @types/react-dom@19 vitest jsdom
```

若 peer 冲突，按 npm 提示用 `--legacy-peer-deps` 仅当必要时。

- [ ] **Step 2: 配置 Vite Tailwind 插件**

`apps/web/vite.config.ts`：

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
  },
});
```

`package.json` scripts 增加：`"test": "vitest run"`。

- [ ] **Step 3: 最小 styles.css**

替换 `apps/web/src/styles.css` 为：

```css
@import "tailwindcss";
@import "@heroui/styles";

html,
body,
#root {
  min-height: 100%;
}

body {
  margin: 0;
}
```

- [ ] **Step 4: 冒烟：临时 Button 能编译**

在 `App.tsx` 顶部临时：

```tsx
import { Button } from "@heroui/react";
// 在某个可见处渲染 <Button>HeroUI OK</Button>
```

运行：

```bash
cd apps/web && npm run build
```

Expected: build 成功。若 `@heroui/react` 无 `Button` 导出名，查 `node_modules/@heroui/react` 的导出并改用实际导出名（后续任务统一跟这个名字）。

确认后**撤掉**临时 Button（下一步会正式用壳层）。

- [ ] **Step 5: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/vite.config.ts apps/web/src/styles.css apps/web/tsconfig.json
git commit -m "chore(web): add HeroUI v3, Tailwind v4, and React 19"
```

---

### Task 2: 主题模块（TDD）

**Files:**
- Create: `apps/web/src/theme/theme.ts`
- Create: `apps/web/src/theme/theme.test.ts`

- [ ] **Step 1: 写失败测试**

`apps/web/src/theme/theme.test.ts`：

```ts
import { describe, it, expect, beforeEach } from "vitest";
import {
  THEME_STORAGE_KEY,
  defaultTheme,
  parseTheme,
  applyTheme,
  readStoredTheme,
  type ThemeId,
} from "./theme";

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("parseTheme accepts desk-dark and desk-light only", () => {
    expect(parseTheme("desk-dark")).toBe("desk-dark");
    expect(parseTheme("desk-light")).toBe("desk-light");
    expect(parseTheme("nope")).toBe(defaultTheme);
    expect(parseTheme(null)).toBe(defaultTheme);
  });

  it("applyTheme sets data-theme and localStorage", () => {
    applyTheme("desk-light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("desk-light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("desk-light");
  });

  it("readStoredTheme falls back to default", () => {
    expect(readStoredTheme()).toBe(defaultTheme);
    localStorage.setItem(THEME_STORAGE_KEY, "desk-light");
    expect(readStoredTheme()).toBe("desk-light");
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/web && npm test
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 theme.ts**

```ts
export type ThemeId = "desk-dark" | "desk-light";

export const THEME_STORAGE_KEY = "desk-theme";
export const defaultTheme: ThemeId = "desk-dark";

/**
 * 解析主题 id；非法值回退默认深色。
 * @param raw localStorage 或属性原始值
 */
export function parseTheme(raw: string | null | undefined): ThemeId {
  if (raw === "desk-dark" || raw === "desk-light") return raw;
  return defaultTheme;
}

/**
 * 读取已存主题。
 */
export function readStoredTheme(): ThemeId {
  try {
    return parseTheme(localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return defaultTheme;
  }
}

/**
 * 应用主题到 documentElement 并持久化。
 * @param theme 主题 id
 */
export function applyTheme(theme: ThemeId): void {
  const next = parseTheme(theme);
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    /* ignore quota / private mode */
  }
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd apps/web && npm test
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/theme apps/web/package.json apps/web/vite.config.ts
git commit -m "feat(web): add desk theme helpers with vitest"
```

---

### Task 3: 主题 CSS 变量 + 首屏 boot

**Files:**
- Modify: `apps/web/src/styles.css`
- Create: `apps/web/src/theme/bootTheme.ts`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/index.html`（可选内联 script；优先 main 最早调用）

- [ ] **Step 1: 扩展 styles.css 主题变量**

在 `@import` 之后追加（保留 Tailwind/HeroUI import）：

```css
html[data-theme="desk-dark"] {
  color-scheme: dark;
  --desk-ink: #07151c;
  --desk-panel: #0d222c;
  --desk-line: #1e4554;
  --desk-mist: #8aa9b5;
  --desk-text: #e7f1f4;
  --desk-accent: #d4a574;
  --desk-signal: #3ecf9a;
  --desk-warn-bg: #3a2a12;
  --desk-warn-fg: #f0d9a0;
  --desk-warn-border: #8a6a2a;
  background: linear-gradient(160deg, #061018, var(--desk-ink));
  color: var(--desk-text);
}

html[data-theme="desk-light"] {
  color-scheme: light;
  --desk-ink: #f4f6f8;
  --desk-panel: #ffffff;
  --desk-line: #e4e4e7;
  --desk-mist: #71717a;
  --desk-text: #18181b;
  --desk-accent: #0f766e;
  --desk-signal: #0d9488;
  --desk-warn-bg: #fff7ed;
  --desk-warn-fg: #9a3412;
  --desk-warn-border: #fdba74;
  background: var(--desk-ink);
  color: var(--desk-text);
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: "Noto Sans SC", system-ui, sans-serif;
  background: transparent;
  color: inherit;
}
```

将 HeroUI 主色尽量对齐 `--desk-accent`（若包支持 CSS 变量覆盖，按官方 Themes 文档设置；否则用 `Button` 的 `className` / Tailwind 着色）。

- [ ] **Step 2: bootTheme.ts**

```ts
import { applyTheme, readStoredTheme } from "./theme";

/**
 * React 挂载前应用主题，减少闪烁。
 */
export function bootTheme(): void {
  applyTheme(readStoredTheme());
}
```

- [ ] **Step 3: main.tsx 最先调用**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { bootTheme } from "./theme/bootTheme";
import "./styles.css";

bootTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

- [ ] **Step 4: build**

```bash
cd apps/web && npm run build
```

Expected: 成功。

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/styles.css apps/web/src/theme apps/web/src/main.tsx
git commit -m "feat(web): desk-dark/light CSS tokens and boot theme"
```

---

### Task 4: AppShell + 瘦身 App 路由

**Files:**
- Create: `apps/web/src/layout/nav.ts`
- Create: `apps/web/src/layout/AppShell.tsx`
- Modify: `apps/web/src/App.tsx`（暂保留页面函数，先换壳）

- [ ] **Step 1: nav.ts**

```ts
export const NAV: { path: string; label: string; end?: boolean }[] = [
  { path: "/", label: "总览", end: true },
  { path: "/market-sync", label: "行情同步" },
  { path: "/watchlist", label: "行情自选" },
  { path: "/sentiment", label: "打板情绪" },
  { path: "/lhb", label: "龙虎榜" },
  { path: "/calendar", label: "日历/停牌" },
  { path: "/strategies", label: "策略" },
  { path: "/factors", label: "因子/ML" },
  { path: "/paper", label: "模拟盘" },
  { path: "/risk", label: "实盘风控" },
  { path: "/alerts", label: "告警" },
  { path: "/ai", label: "投研 nanobot" },
  { path: "/morning", label: "晨会" },
  { path: "/review", label: "复盘" },
  { path: "/knowledge", label: "知识库" },
];
```

- [ ] **Step 2: 实现 AppShell**

要点（组件名以 Task 1 确认的 `@heroui/react` 导出为准）：

- 左侧栏：品牌「刻度·Desk」、`NavLink` 列表、底部主题切换（Switch 或两个 Button）
- 主区：`<h1>{title}</h1>`、DB/API `Alert`、健康 `Chip`、`{children}`、底部 log 文案
- props：`title`、`health`、`healthError`、`log`、`theme`、`onThemeChange`、`children`
- 布局用 Tailwind：`grid grid-cols-[220px_1fr] min-h-screen`；`max-md:grid-cols-1`

主题切换调用 `applyTheme` 并 `onThemeChange`。

健康轮询逻辑可仍留在 `App.tsx`，通过 props 传入。

- [ ] **Step 3: App.tsx 改用 AppShell**

用 `AppShell` 包住现有 `Routes`；删除旧 `.nav` / `.main` DOM 结构。页面内容暂时仍可是旧 class（下一任务再迁）。

- [ ] **Step 4: build + 手工点开 `/` 与 `/market-sync`，切换主题**

Expected: 壳层 HeroUI 样式生效；主题切换刷新仍保留。

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/layout apps/web/src/App.tsx
git commit -m "feat(web): HeroUI AppShell with theme toggle"
```

---

### Task 5: 拆出并迁移高频页（Overview / MarketSync / Watchlist）

**Files:**
- Create: `apps/web/src/pages/Overview.tsx`
- Modify: `apps/web/src/pages/MarketSync.tsx`
- Create: `apps/web/src/pages/Watchlist.tsx`
- Modify: `apps/web/src/App.tsx`（import 页面，删除内联组件）

- [ ] **Step 1: 抽出 Overview**

把 `Overview` 移到 `pages/Overview.tsx`；UI 用 `Card` + `Button` + 文案；`setLog` prop 保留。

- [ ] **Step 2: MarketSync 换 HeroUI**

按钮组 → `Button`；任务表 → `Table`（或 HeroUI 表格复合组件；若无 Table 则用 Tailwind `table` + HeroUI `Chip` 表示 status）；保留 `/api/market/jobs/*` 与 2s 轮询。

- [ ] **Step 3: Watchlist 换 HeroUI**

刷新按钮 + 自选表；逻辑不变。

- [ ] **Step 4: 更新 Routes import；build**

```bash
cd apps/web && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages apps/web/src/App.tsx
git commit -m "feat(web): HeroUI Overview, MarketSync, Watchlist pages"
```

---

### Task 6: 迁移其余全部页面

**Files:**
- Create: `apps/web/src/pages/Sentiment.tsx`
- Create: `apps/web/src/pages/Lhb.tsx`
- Create: `apps/web/src/pages/Calendar.tsx`
- Create: `apps/web/src/pages/Strategies.tsx`
- Create: `apps/web/src/pages/Factors.tsx`
- Create: `apps/web/src/pages/Paper.tsx`
- Create: `apps/web/src/pages/Risk.tsx`
- Create: `apps/web/src/pages/Alerts.tsx`
- Create: `apps/web/src/pages/Research.tsx`
- Create: `apps/web/src/pages/Morning.tsx`
- Create: `apps/web/src/pages/Review.tsx`
- Create: `apps/web/src/pages/Knowledge.tsx`
- Modify: `apps/web/src/App.tsx`（仅壳 + Routes，无业务组件）

- [ ] **Step 1: 逐页从 App.tsx 剪切到 `pages/`，替换为 HeroUI**

映射规则见 spec §组件映射。JSON 展示用 `Code` / `<pre className="...">` + Tailwind。`Input`/`Textarea` 用于投研与表单。

每迁 3～4 个页面可中间 build 一次，避免堆积错误。

- [ ] **Step 2: App.tsx 最终形态**

仅：`NAV` 已外置、`AppShell`、health 轮询、`Routes` 指向 `pages/*`、`Navigate` fallback。

- [ ] **Step 3: 路由清单核对**

手工或脚本确认以下 path 均有对应 Route：  
`/` `/market-sync` `/watchlist` `/sentiment` `/lhb` `/calendar` `/strategies` `/factors` `/paper` `/risk` `/alerts` `/ai` `/morning` `/review` `/knowledge`

- [ ] **Step 4: build**

```bash
cd apps/web && npm run build && npm test
```

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add apps/web/src
git commit -m "feat(web): migrate remaining pages to HeroUI"
```

---

### Task 7: 清理旧样式与验收

**Files:**
- Modify: `apps/web/src/styles.css`（删除 `.btn` `.card` `.nav` 等旧规则；只留 Tailwind/HeroUI/主题/少量布局 utility）
- Modify: spec 状态行（可选）`docs/superpowers/specs/2026-07-16-heroui-web-refactor-design.md` → 状态实现中/完成

- [ ] **Step 1: ripgrep 确认无业务依赖旧 class**

```bash
cd apps/web
rg "className=.*(btn|card|stack|banner|muted|mono)" src --glob "*.tsx"
```

Expected: 无关键旧 class（`mono` 若仍用可改为 Tailwind `font-mono`）。

- [ ] **Step 2: 验收清单（手工）**

1. `npm run build` 通过  
2. 全部路由可进，刷新 URL 不变  
3. 主题切换即时 + localStorage 保留  
4. 停掉 Postgres 或 mock `db:false` 时 Alert 可见（或临时改 health 展示逻辑验证 UI）  
5. `/market-sync` 点「刷新状态」与入队按钮行为正常  

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/styles.css docs/superpowers/specs/2026-07-16-heroui-web-refactor-design.md
git commit -m "chore(web): remove legacy CSS after HeroUI migration"
```

---

## Spec coverage check

| Spec 要求 | Task |
|-----------|------|
| HeroUI v3 + Tailwind v4 + React 19 | Task 1 |
| desk-dark / desk-light + localStorage | Task 2–3 |
| 左侧栏 + 底部主题切换 | Task 4 |
| 全量页面迁移 | Task 5–6 |
| 删除旧 `.btn`/`.card` | Task 7 |
| 路由刷新保留 | 已有 Router；Task 4–6 保持 path |
| DB Alert | Task 4 |
| build 验收 | Task 1/5/6/7 |

## Agent notes

- HeroUI v3 具体导出以安装后的包为准；若无 `Table`/`Card` 复合组件，用官方文档中的等价组件或 Tailwind + `Button`/`Alert`/`Chip` 组合，勿阻塞全量迁移。
- 用户规则：不要在后台常驻启动 `vite`/`uvicorn`；验收时前台短跑或用户本机已开的服务。
- 回答与注释：简体中文；新函数用 JSDoc。
