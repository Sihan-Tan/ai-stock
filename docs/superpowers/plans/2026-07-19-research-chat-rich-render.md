# 投研对话助手消息富文本展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 投研页助手消息在流式结束后以 Markdown/JSON 富文本展示，流式过程保持纯文本。

**Architecture:** 抽出 `detectContentKind` 与 `AssistantMessageBody`；流式用 `<pre>`，结束后用 `react-markdown`+`remark-gfm` 或可折叠 JSON 代码块。样式走 `.research-md` + desk CSS 变量（舒适密度）。不改 API。

**Tech Stack:** React 19、Vitest、`react-markdown`、`remark-gfm`；JSON 用格式化 `<pre>` + 折叠条（不在气泡内挂 CodeMirror，避免为聊天再加 `@codemirror/lang-json`）。

**Spec:** `docs/superpowers/specs/2026-07-19-research-chat-rich-render-design.md`

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| Create: `apps/web/src/pages/detectContentKind.ts` | 内容类型检测 + JSON 美化辅助 |
| Create: `apps/web/src/pages/detectContentKind.test.ts` | 单测 |
| Create: `apps/web/src/pages/JsonCodeBlock.tsx` | 可折叠格式化 JSON 面板 |
| Create: `apps/web/src/pages/AssistantMessageBody.tsx` | 流式/完成态渲染入口 |
| Create: `apps/web/src/pages/AssistantMessageBody.test.ts` | 流式 vs 表格 DOM 单测（`renderToStaticMarkup`） |
| Modify: `apps/web/src/pages/Research.tsx` | 助手气泡改用 `AssistantMessageBody` |
| Modify: `apps/web/src/styles.css` | `.research-md` / `.research-json` 舒适密度样式 |
| Modify: `apps/web/package.json` | 增加 `react-markdown`、`remark-gfm` |
| Modify: `apps/web/vite.config.ts` | 若需支持从 `.test.ts` 测 JSX，保持现状即可（`.ts` 可 import `.tsx`） |

---

### Task 1: `detectContentKind` 与 JSON 美化

**Files:**
- Create: `apps/web/src/pages/detectContentKind.ts`
- Create: `apps/web/src/pages/detectContentKind.test.ts`

- [ ] **Step 1: 写失败单测**

```typescript
import { describe, expect, it } from "vitest";
import { detectContentKind, formatJsonText, JSON_COLLAPSE_THRESHOLD } from "./detectContentKind";

describe("detectContentKind", () => {
  it("detects object and array JSON", () => {
    expect(detectContentKind('{"a":1}')).toBe("json");
    expect(detectContentKind("  [1, 2]  ")).toBe("json");
  });

  it("treats invalid JSON and markdown as markdown", () => {
    expect(detectContentKind("{not json")).toBe("markdown");
    expect(detectContentKind("## 标题\n- 列表")).toBe("markdown");
    expect(detectContentKind("")).toBe("markdown");
  });
});

describe("formatJsonText", () => {
  it("pretty-prints valid JSON", () => {
    expect(formatJsonText('{"a":1}')).toBe('{\n  "a": 1\n}');
  });

  it("returns original text when parse fails", () => {
    expect(formatJsonText("{x")).toBe("{x");
  });
});

describe("JSON_COLLAPSE_THRESHOLD", () => {
  it("is 100KB", () => {
    expect(JSON_COLLAPSE_THRESHOLD).toBe(100_000);
  });
});
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd apps/web && npm test -- src/pages/detectContentKind.test.ts`

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```typescript
/** 整段内容类型：纯 JSON 或按 Markdown 处理 */
export type ContentKind = "json" | "markdown";

/** 超过该字符数的 JSON 默认折叠（100KB） */
export const JSON_COLLAPSE_THRESHOLD = 100_000;

/**
 * 检测助手消息内容类型。
 * @param text 原始文本
 */
export function detectContentKind(text: string): ContentKind {
  const trimmed = text.trim();
  if (!trimmed) return "markdown";
  if (trimmed[0] !== "{" && trimmed[0] !== "[") return "markdown";
  try {
    JSON.parse(trimmed);
    return "json";
  } catch {
    return "markdown";
  }
}

/**
 * 美化 JSON 文本；解析失败则原样返回。
 * @param text 原始文本
 */
export function formatJsonText(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text.trim()), null, 2);
  } catch {
    return text;
  }
}

/**
 * 尝试解析 JSON；失败返回 null。
 * @param text 原始文本
 */
export function tryParseJson(text: string): unknown | null {
  try {
    return JSON.parse(text.trim());
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: 跑测确认通过**

Run: `cd apps/web && npm test -- src/pages/detectContentKind.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/detectContentKind.ts apps/web/src/pages/detectContentKind.test.ts
git commit -m "feat(web): 投研消息内容类型检测与 JSON 美化"
```

---

### Task 2: 安装 Markdown 依赖

**Files:**
- Modify: `apps/web/package.json`

- [ ] **Step 1: 安装**

Run: `cd apps/web && npm install react-markdown remark-gfm`

Expected: `package.json` / `package-lock.json` 出现上述依赖

- [ ] **Step 2: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json
git commit -m "chore(web): 添加 react-markdown 与 remark-gfm"
```

---

### Task 3: `JsonCodeBlock` 可折叠面板

**Files:**
- Create: `apps/web/src/pages/JsonCodeBlock.tsx`

- [ ] **Step 1: 实现组件**

```tsx
import { useState } from "react";
import { formatJsonText, JSON_COLLAPSE_THRESHOLD } from "./detectContentKind";

type Props = {
  /** 原始 JSON 文本（可为未格式化） */
  text: string;
  /** 强制默认折叠；缺省时按长度阈值 */
  defaultCollapsed?: boolean;
};

/**
 * 格式化 JSON 可折叠代码块。
 * @param props.text 原始文本
 * @param props.defaultCollapsed 是否默认折叠
 */
export function JsonCodeBlock({ text, defaultCollapsed }: Props) {
  const pretty = formatJsonText(text);
  const autoCollapse = pretty.length >= JSON_COLLAPSE_THRESHOLD;
  const [open, setOpen] = useState(!(defaultCollapsed ?? autoCollapse));

  return (
    <div className="research-json overflow-hidden rounded-lg border border-[var(--desk-line)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 bg-[var(--desk-ink)] px-3 py-1.5 text-left text-[11px] text-[var(--desk-mist)]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>JSON · 已格式化</span>
        <span>{open ? "▾ 折叠" : "▸ 展开"}</span>
      </button>
      {open ? (
        <pre className="m-0 max-h-[min(50vh,420px)] overflow-auto bg-[var(--desk-panel)] px-3 py-2 font-mono text-xs leading-relaxed text-[var(--desk-text)] whitespace-pre">
          {pretty}
        </pre>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/pages/JsonCodeBlock.tsx
git commit -m "feat(web): 投研 JSON 可折叠代码块"
```

---

### Task 4: `AssistantMessageBody` + 样式 + 组件测

**Files:**
- Create: `apps/web/src/pages/AssistantMessageBody.tsx`
- Create: `apps/web/src/pages/AssistantMessageBody.test.ts`
- Modify: `apps/web/src/styles.css`（文件末尾追加 `.research-md` 规则）

- [ ] **Step 1: 写失败组件测**

```typescript
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AssistantMessageBody } from "./AssistantMessageBody";

const tableMd = `| 指标 | 数值 |
| --- | --- |
| PE | 28 |`;

describe("AssistantMessageBody", () => {
  it("keeps plain text while streaming", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, { content: tableMd, streaming: true }),
    );
    expect(html).not.toContain("<table");
    expect(html).toContain("<pre");
  });

  it("renders markdown table when done", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, { content: tableMd, streaming: false }),
    );
    expect(html).toContain("<table");
  });

  it("renders json panel for whole-message JSON", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, {
        content: '{"symbol":"600519"}',
        streaming: false,
      }),
    );
    expect(html).toContain("JSON");
    expect(html).toContain("600519");
  });

  it("shows ellipsis placeholder when streaming empty", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, { content: "", streaming: true }),
    );
    expect(html).toContain("…");
  });
});
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd apps/web && npm test -- src/pages/AssistantMessageBody.test.ts`

Expected: FAIL（组件不存在）

- [ ] **Step 3: 实现 `AssistantMessageBody.tsx`**

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { detectContentKind, tryParseJson } from "./detectContentKind";
import { JsonCodeBlock } from "./JsonCodeBlock";

type Props = {
  content: string;
  streaming: boolean;
};

const mdComponents: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  code: ({ className, children, ...rest }) => {
    const text = String(children).replace(/\n$/, "");
    const lang = /language-(\w+)/.exec(className || "")?.[1];
    const isBlock = Boolean(className) || text.includes("\n");
    if (isBlock && lang === "json" && tryParseJson(text) !== null) {
      return <JsonCodeBlock text={text} />;
    }
    if (isBlock) {
      return (
        <pre className="research-md-pre">
          <code className={className} {...rest}>
            {children}
          </code>
        </pre>
      );
    }
    return (
      <code className="research-md-inline-code" {...rest}>
        {children}
      </code>
    );
  },
};

/**
 * 助手消息体：流式纯文本，完成后 Markdown/JSON。
 * @param props.content 消息文本
 * @param props.streaming 是否仍在流式生成
 */
export function AssistantMessageBody({ content, streaming }: Props) {
  if (streaming) {
    return (
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-[var(--desk-text)]">
        {content || "…"}
      </pre>
    );
  }

  if (!content.trim()) {
    return (
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-[var(--desk-text)]" />
    );
  }

  if (detectContentKind(content) === "json") {
    return <JsonCodeBlock text={content} />;
  }

  return (
    <div className="research-md text-sm text-[var(--desk-text)]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
```

- [ ] **Step 4: 在 `apps/web/src/styles.css` 末尾追加**

```css
/* 投研助手 Markdown（舒适密度） */
.research-md {
  line-height: 1.6;
}
.research-md > :first-child {
  margin-top: 0;
}
.research-md > :last-child {
  margin-bottom: 0;
}
.research-md h1 {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 1rem 0 0.5rem;
}
.research-md h2 {
  font-size: 1.1rem;
  font-weight: 650;
  margin: 0.9rem 0 0.45rem;
}
.research-md h3 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0.75rem 0 0.35rem;
}
.research-md p {
  margin: 0.45rem 0;
}
.research-md ul,
.research-md ol {
  margin: 0.4rem 0;
  padding-left: 1.25rem;
}
.research-md li {
  margin: 0.2rem 0;
}
.research-md table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.6rem 0;
  font-size: 0.8125rem;
}
.research-md th,
.research-md td {
  border-bottom: 1px solid var(--desk-line);
  padding: 0.4rem 0.5rem;
  text-align: left;
  vertical-align: top;
}
.research-md th {
  color: var(--desk-mist);
  font-weight: 600;
}
.research-md-pre {
  margin: 0.5rem 0;
  overflow-x: auto;
  border-radius: 0.5rem;
  border: 1px solid var(--desk-line);
  background: var(--desk-ink);
  padding: 0.65rem 0.75rem;
  font-size: 0.75rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.research-md-inline-code {
  border-radius: 0.25rem;
  background: var(--desk-ink);
  padding: 0.1rem 0.3rem;
  font-size: 0.85em;
}
.research-md a {
  color: var(--desk-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.research-md blockquote {
  margin: 0.5rem 0;
  border-left: 3px solid var(--desk-line);
  padding-left: 0.75rem;
  color: var(--desk-mist);
}
```

- [ ] **Step 5: 跑测确认通过**

Run: `cd apps/web && npm test -- src/pages/AssistantMessageBody.test.ts src/pages/detectContentKind.test.ts`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/AssistantMessageBody.tsx apps/web/src/pages/AssistantMessageBody.test.ts apps/web/src/styles.css
git commit -m "feat(web): 助手消息 Markdown/JSON 渲染组件"
```

---

### Task 5: 接入 `Research.tsx`

**Files:**
- Modify: `apps/web/src/pages/Research.tsx`

- [ ] **Step 1: 增加 import**

在文件顶部其它 import 旁加入：

```tsx
import { AssistantMessageBody } from "./AssistantMessageBody";
```

- [ ] **Step 2: 替换助手/用户气泡内容渲染**

将 `messages.map` 内的内容区改为（用户仍用 `<pre>`，助手用组件）：

```tsx
{messages.map((msg, index) => {
  const streaming =
    busy && index === messages.length - 1 && msg.role === "assistant";
  return (
    <div
      key={`${msg.role}-${index}`}
      className={
        msg.role === "user"
          ? "ml-6 rounded-lg border border-[var(--desk-accent)]/35 bg-[var(--desk-panel)] px-3 py-2.5 sm:ml-12"
          : "mr-4 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)]/40 px-3 py-2.5"
      }
    >
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-[var(--desk-mist)]">
        {msg.role === "user" ? "你" : "助手"}
      </div>
      {msg.role === "assistant" ? (
        <AssistantMessageBody content={msg.content} streaming={streaming} />
      ) : (
        <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-[var(--desk-text)]">
          {msg.content}
        </pre>
      )}
    </div>
  );
})}
```

- [ ] **Step 3: 跑全量前端测**

Run: `cd apps/web && npm test`

Expected: PASS

- [ ] **Step 4: 类型检查（可选但建议）**

Run: `cd apps/web && npx tsc -b --pretty false`

Expected: 无 error

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/Research.tsx
git commit -m "feat(web): 投研对话助手气泡接入富文本渲染"
```

---

### Task 6: 手工验收清单

- [ ] **Step 1: 确认开发服务已由用户启动（勿后台擅自启动）**；打开投研页
- [ ] **Step 2: 发送含 Markdown 的问题（或快捷「五步法」）** → 流式为纯文本；结束后出现标题/列表/表格样式
- [ ] **Step 3: 若有整段 JSON 回复（或临时 mock）** → 出现「JSON · 已格式化」可折叠块
- [ ] **Step 4: 确认用户气泡仍为纯文本**

无需额外 commit（无代码变更时跳过）。

---

## Spec Coverage Check

| Spec 要求 | Task |
| --- | --- |
| 仅助手渲染 | Task 5 |
| 流式纯文本、结束富文本 | Task 4–5 |
| Markdown + GFM 表格 | Task 2、4 |
| 整段 JSON 格式化可折叠 | Task 1、3、4 |
| 围栏 json → JsonCodeBlock | Task 4 `mdComponents.code` |
| 100KB 默认折叠 | Task 1/3 `JSON_COLLAPSE_THRESHOLD` |
| 外链 noopener | Task 4 `a` 组件 |
| 舒适密度样式 | Task 4 CSS |
| 不改 API | 全计划无后端改动 |
| 单测 detect + streaming/table | Task 1、4 |

## Placeholder / Consistency Self-Review

- 无 TBD；组件名与路径与 spec 一致：`AssistantMessageBody`、`detectContentKind`、`JsonCodeBlock`。
- JSON 展示明确采用格式化 `<pre>`（spec 允许的轻量路径），不引入 `@codemirror/lang-json`。
