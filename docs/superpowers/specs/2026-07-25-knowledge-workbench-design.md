# 知识库完善：工作台 + PDF + 可切换检索

**日期：** 2026-07-25  
**状态：** 已实现  
**入口：** 导航「知识库」；投研工具 `search_knowledge`  
**前置：** 现有 `KnowledgeStore`（文件 + `knowledge_docs` / `knowledge_chunks`）

## 目标

1. 将知识库页做成可用工作台：列表、详情、新建/编辑、删除、页内检索。  
2. 支持上传 **PDF / Markdown / 纯文本**（含股票相关书籍资料）；PDF 文本抽取入库并切片。  
3. 检索可配置：**关键词（默认）**、**云端向量**、**混合**；无 embedding Key 时关键词仍可用。

## 非目标

- OCR / 扫描版 PDF（无文字层则明确提示失败）  
- **纯本地 sentence-transformers 向量**（记入 `docs/TODO.md`，下期）  
- 多用户权限、在线协作、富文本所见即所得  
- 自动从互联网爬书籍

## 已确认决策

| 项 | 选择 |
| --- | --- |
| 工作台 | 列表 / 详情 / 新建 / 编辑 / 删除 + 页内搜索 |
| 上传 | `.pdf` / `.md` / `.txt`；multipart |
| PDF | `pypdf` 抽文本；无文本 → 错误提示 |
| 检索 | `keyword` \| `vector` \| `hybrid` 可配置；1+2 可切换 |
| Embedding | 云端 API（可独立配置，空则回退 `LLM_*`）；无 Key 时禁止 vector、hybrid 降级或报错（见下） |
| 本地向量模型 | **不做**，TODO |
| upsert | 同 `doc_id` 更新正文并**重建** chunks（及向量） |

## 数据与切片

### 存储

- 文件：`data/knowledge/{doc_id}.pdf|.md|.txt`（扩展名随类型）  
- DB：`knowledge_docs`（已有字段 + 可选 `updated_at` 若易加）  
- DB：`knowledge_chunks`（已有 `embedding_ref`）  
- 向量：本地 `data/knowledge/embeddings/{doc_id}.npz`（每行/数组对齐 chunk_index）；`embedding_ref` 存相对路径或 `npy:{doc_id}`

### 切片规则

- 目标长度约 **800** 字，重叠约 **100**  
- PDF：按页抽取后拼接，再按字切片；chunk meta 可在 content 前缀标注页码（实现计划写死格式）  
- 空正文不得入库

### `doc_type`

| 值 | 含义 |
| --- | --- |
| `markdown` / `note` | 手写笔记 |
| `pdf` | PDF 书籍/资料 |
| `research_note` | 投研工具保存（保持兼容） |
| `text` | 纯文本上传 |

## 检索

### 配置

| 字段 | 环境变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| `knowledge_retrieval` | `KNOWLEDGE_RETRIEVAL` | `keyword` | `keyword` / `vector` / `hybrid` |
| `embedding_api_key` | `EMBEDDING_API_KEY` | 空 | 空则回退 `LLM_API_KEY` |
| `embedding_base_url` | `EMBEDDING_BASE_URL` | 空 | 空则回退 `LLM_BASE_URL` |
| `embedding_model` | `EMBEDDING_MODEL` | 空 | 如 `text-embedding-3-small`；空则厂商默认或禁用向量 |

行为：

- `keyword`：jieba 分词 + 命中计分（增强现网简易 `in` 匹配）  
- `vector`：无可用 embedding → **400/明确错误**「未配置 embedding」  
- `hybrid`：无 embedding → **自动降级 keyword** 并在结果带 `mode_used=keyword`；有则向量分与关键词分加权（如 0.7/0.3，计划写死）

`POST /search` 可选 `mode` 覆盖全局一次查询。

### 投研

`search_knowledge` 调用同一 `KnowledgeStore.search`，尊重全局模式（工具参数可不传 mode）。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge/docs` | 列表（含 `chunk_count`、`updated` 若有） |
| GET | `/api/knowledge/docs/{doc_id}` | 详情：元数据 + 全文或前 N 字 + chunks 摘要 |
| POST | `/api/knowledge/docs` | JSON 新建（现有） |
| PUT | `/api/knowledge/docs/{doc_id}` | 更新标题/标签/正文并重建切片 |
| DELETE | `/api/knowledge/docs/{doc_id}` | 删 DB + 文件 + 向量 |
| POST | `/api/knowledge/docs/upload` | multipart：`file` + 可选 `title`/`tags` |
| POST | `/api/knowledge/search` | `query`/`top_k`/`mode?` |

设置页或 `.env`：检索模式与 embedding 三项；写入 `settings` / `settings_store` / `.env.example`。

## UI（知识库页）

对齐现有 Desk 面板风格（非营销落地页）：

1. **顶栏**：新建笔记、上传文件、刷新  
2. **左/上**：文档列表（标题、类型 Chip、标签、切片数）  
3. **右/下**：详情（正文预览、编辑、删除）  
4. **检索区**：输入框 + 模式提示；结果列表可点进文档  

去掉「仅上传示例 + 整页 JSON」的临时形态（示例按钮可保留为次要「插入示例」）。

## 组件边界

| 单元 | 职责 |
| --- | --- |
| `KnowledgeStore` | upsert/update/delete/list/get、切片、检索调度 |
| PDF 抽取 | 小模块或 store 内 `_extract_pdf` |
| Embedding 客户端 | 调用 OpenAI 兼容 `/embeddings` |
| routes/knowledge | REST |
| Knowledge.tsx | 工作台 UI |
| Settings | 检索模式 + embedding 配置（可放「投研」或独立小块） |

## 验收

1. 上传 PDF 后列表出现 `doc_type=pdf`，详情可见抽取文本预览与 chunk 数  
2. 无 embedding Key：`keyword` 搜索可用；`vector` 返回明确错误；`hybrid` 降级 keyword  
3. 配置 embedding 后：新文档入库生成向量；`hybrid`/`vector` 可命中语义相关段落  
4. 编辑/删除后检索结果一致；投研 `search_knowledge` 仍可用  
5. 扫描件 PDF（无文本）上传失败提示可读  

## 开放实现细节（计划写死）

- jieba 是否必选依赖（建议可选：无 jieba 时回退空白/`re` 分词）  
- 大 PDF 同步上传超时：首版同步 + 前端 busy；单文件大小上限（如 30MB）  
- embedding 批大小与失败重试  
- `GET` 详情是否返回全文（大书建议截断 +「下载原文件」链接可选）

## 后续 TODO（不在本期）

- 纯本地 `sentence-transformers` 向量索引（离线部署）
