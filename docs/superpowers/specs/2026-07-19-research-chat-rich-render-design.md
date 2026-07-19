# 投研对话助手消息富文本展示

## 背景

投研页助手回复常为 Markdown 报告或 JSON。当前用 `<pre>` 纯文本展示，标题、列表、表格难扫读。需要在不影响流式稳定性的前提下，提升完成后的可读性。

## 目标

- 助手消息在**生成结束后**按内容类型富文本展示（Markdown / JSON）。
- 用户消息保持现状（纯文本）。
- 视觉密度采用**舒适**档：标题层级清晰、表格有分隔线，便于扫读报告。

## 非目标

- 不改后端 API / Agent / Skills。
- 不做用户消息 Markdown 渲染。
- 不做 JSON 树形视图（仅格式化高亮代码块 + 折叠）。
- 不做流式过程中的实时 Markdown 渲染。

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 渲染范围 | 仅助手消息 |
| 流式策略 | 生成中纯文本；结束后一次切换富文本 |
| JSON 展示 | 格式化 + 语法高亮/只读代码块，可折叠 |
| 技术方案 | `react-markdown` + `remark-gfm`；JSON 优先复用现有 CodeMirror 只读或等价轻量高亮 |
| 视觉密度 | 舒适（B） |

## 架构

### 组件

- `AssistantMessageBody`（建议路径：`apps/web/src/pages/AssistantMessageBody.tsx`）
  - props：`content: string`、`streaming: boolean`
  - `streaming === true`：现有纯文本 `<pre>`（含「…」占位）
  - `streaming === false`：按内容类型渲染

- `detectContentKind(text: string): "json" | "markdown"`
  - 去掉首尾空白后，若以 `{` 或 `[` 开头且 `JSON.parse` 成功 → `"json"`
  - 否则 → `"markdown"`

- `JsonCodeBlock`
  - `JSON.stringify(parsed, null, 2)` 展示
  - 默认可展开；提供折叠控件（标题栏显示 `JSON · 已格式化`）
  - 只读，便于复制

- Markdown：`react-markdown` + `remark-gfm`
  - 支持标题、列表、表格、围栏代码块、链接
  - 围栏语言为 `json` 的代码块：走 `JsonCodeBlock`（parse 失败则普通代码块）
  - 不启用原始 HTML 透传

### 样式

- 容器 class：`research-md`（及 JSON 面板专用 class）
- 使用现有 CSS 变量：`--desk-text`、`--desk-mist`、`--desk-line`、`--desk-panel`、`--desk-ink`、`--desk-accent`
- 舒适密度约定：
  - `h1`/`h2`/`h3` 有明确字号阶梯与上下边距
  - 段落行高约 1.55–1.65
  - 表格：表头底边框 + 行分隔，单元格有内边距
  - 代码块：圆角 + 边框 + 与气泡背景区分的底色

### 接入点

- `Research.tsx` 助手气泡内：用 `AssistantMessageBody` 替换当前助手侧 `<pre>`
- `streaming` 判定：`busy && index === messages.length - 1 && msg.role === "assistant"`

## 数据流

1. 用户发送 → 追加 user + 空 assistant → `busy=true`
2. 流式追加 assistant.content → `AssistantMessageBody` 以 `streaming` 纯文本显示
3. 流结束 → `busy=false` → 该条以 `done` 富文本渲染
4. 历史消息（含新会话前已有）始终 `streaming=false`

## 边界与错误处理

| 情况 | 行为 |
| --- | --- |
| 空内容或仅加载占位 | 不进入 Markdown/JSON 组件，显示占位或空 |
| 整段伪 JSON（parse 失败） | 按 Markdown 渲染 |
| Markdown 内 json 围栏 parse 失败 | 普通代码块 |
| 超长 JSON（建议阈值 100KB 字符） | 仍格式化，**默认折叠**，避免气泡过高 |
| 外链 | `target="_blank"` + `rel="noopener noreferrer"` |

## 依赖

- 新增：`react-markdown`、`remark-gfm`（仅 `apps/web`）
- JSON 展示：优先 `@uiw/react-codemirror` 只读 + JSON 语言支持（若包体积/只读模式不合适，则用带 desk 主题的 `<pre>` + 简单关键字着色，不引入第二套高亮体系）

## 测试

- 单测 `detectContentKind`：合法 JSON 对象/数组、非法 JSON、纯 Markdown、前后空白
- 单测/组件测：`streaming=true` 时不出现表格 DOM；`streaming=false` 且含 `|` 表格语法时出现 `table`
- 手工：快捷提示跑一条五步法报告，确认结束后标题/列表/表格可读；整段 JSON 可折叠

## 验收标准

1. 助手流式过程中仍为纯文本，页面不因半截 Markdown 抖动错乱。
2. 结束后 Markdown 报告出现层级标题、列表、表格样式（舒适密度）。
3. 整段 JSON 助手回复显示为格式化、可折叠代码块。
4. 用户气泡无变化；API 无变更。
