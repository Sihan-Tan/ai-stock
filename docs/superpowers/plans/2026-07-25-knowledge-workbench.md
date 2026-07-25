# 知识库工作台 + PDF + 可切换检索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识库 CRUD 工作台、PDF/md/txt 上传切片、keyword/vector/hybrid 检索（云端 embedding 可选）；投研 `search_knowledge` 共用同一检索。

**Architecture:** 扩展 `KnowledgeStore`（真 upsert/delete、PDF 抽取、切片、检索调度）；`embedding` 小模块调 OpenAI 兼容 API；向量存 `data/knowledge/embeddings/{doc_id}.npy`；REST 补齐；重写 `Knowledge.tsx`；Settings 增加检索/embedding 配置。

**Tech Stack:** FastAPI、SQLAlchemy、pypdf、可选 jieba、numpy、OpenAI SDK、React、pytest

**Spec:** `docs/superpowers/specs/2026-07-25-knowledge-workbench-design.md`

**约定：** 仅用户要求时 commit。Python docstring；前端 JSDoc。

**写死的开放项：**

| 项 | 决定 |
| --- | --- |
| 分词 | 优先 `jieba`；未安装则 `re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]+', q)` |
| 单文件上限 | **30MB** |
| 详情正文 | 返回 `content_preview` 最多 **20000** 字 + `content_truncated`；全文读文件仅编辑时再拉或同接口 `full=1` |
| hybrid 权重 | 向量 **0.7** + 关键词 **0.3**（归一化后加权） |
| 向量存储 | `numpy.save` → `data/knowledge/embeddings/{doc_id}.npy`；shape `(n_chunks, dim)` |
| 依赖 | `pyproject.toml` 增加 `pypdf`；`jieba` 为 optional extra 或直接依赖（计划：**直接依赖 jieba** 简化） |

---

## File Structure

| 路径 | 职责 |
| --- | --- |
| Modify: `packages/knowledge/desk_knowledge/__init__.py` | Store CRUD + search 调度 |
| Create: `packages/knowledge/desk_knowledge/pdf_extract.py` | PDF → text |
| Create: `packages/knowledge/desk_knowledge/chunking.py` | 800/100 切片 |
| Create: `packages/knowledge/desk_knowledge/retrieve.py` | keyword / vector / hybrid |
| Create: `packages/knowledge/desk_knowledge/embeddings.py` | 云端 embedding + npy IO |
| Modify: `packages/db/desk_db/models.py` | `KnowledgeDoc.updated_at` 可选 |
| Create: `alembic/versions/0012_knowledge_updated_at.py` | 若加列 |
| Modify: `packages/common/.../settings.py` + store + routes/settings | 检索/embedding 配置 |
| Modify: `apps/api/app/routes/knowledge.py` | REST 全量 |
| Modify: `apps/web/src/pages/Knowledge.tsx` | 工作台 UI |
| Modify: `.env.example` | 新键中文注释 |
| Test: `tests/test_knowledge_store.py` 等 | TDD |

---

### Task 1: 切片 + PDF 抽取 + 真 upsert/delete

**Files:**
- Create: `packages/knowledge/desk_knowledge/chunking.py`
- Create: `packages/knowledge/desk_knowledge/pdf_extract.py`
- Modify: `packages/knowledge/desk_knowledge/__init__.py`
- Test: `tests/test_knowledge_store.py`
- Modify: `pyproject.toml`（pypdf、jieba）

- [ ] **Step 1: 写失败单测**

```python
from desk_knowledge.chunking import chunk_text
from desk_knowledge.pdf_extract import extract_pdf_text

def test_chunk_overlap():
    text = "字" * 1000
    parts = chunk_text(text, size=800, overlap=100)
    assert len(parts) >= 2
    assert parts[0][-100:] == parts[1][:100] or len(parts[0]) == 800

def test_upsert_update_rebuilds_chunks(db):
    store = KnowledgeStore(db)
    a = store.upsert("t", "hello world " * 50, tags="a")
    b = store.update(a["doc_id"], title="t2", content="new content only", tags="b")
    assert b["doc_id"] == a["doc_id"]
    docs = store.list_docs()
    assert sum(1 for d in docs if d["doc_id"] == a["doc_id"]) == 1

def test_delete_removes_file_and_chunks(db, tmp_path, monkeypatch):
    ...
```

- [ ] **Step 2: 实现 `chunk_text`、`extract_pdf_text`（无字 raise ValueError）**

- [ ] **Step 3: Store API**

```python
def upsert(...)  # 保持新建；或改为若传 doc_id 则 update
def create(...)
def update(doc_id, title, content, tags, doc_type=...)
def delete(doc_id) -> None
def get(doc_id, *, full: bool = False) -> dict
def list_docs() -> list  # 增加 chunk_count
```

`upsert` 兼容旧调用（总是新建）；投研 `save_research_note` 仍调 upsert。  
`update`/`create` 写文件、删旧 chunks、重切。  
`delete`：删 chunks、doc、文件、embeddings npy（若存在）。

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit**（仅用户要求时）

---

### Task 2: keyword 检索增强

**Files:**
- Create: `packages/knowledge/desk_knowledge/retrieve.py`
- Modify: Store.search → 调 retrieve
- Test: `tests/test_knowledge_retrieve.py`

- [ ] **Step 1: 单测** — 中文查询能命中切片；空 query → []

```python
def test_keyword_search_hits_chinese(db):
    store.upsert("情绪", "高位晋级率连续两日低于百分之三十则退潮", tags="情绪")
    hits = store.search("晋级率 退潮", top_k=3, mode="keyword")
    assert hits and "晋级率" in hits[0]["content"]
```

- [ ] **Step 2: 实现 tokenize + score；search(mode=) 签名**

返回字段：`doc_id, chunk_index, content, score, title?, tags?, mode_used`

- [ ] **Step 3: PASS + Commit**（按约定）

---

### Task 3: Embedding 客户端 + vector/hybrid

**Files:**
- Create: `packages/knowledge/desk_knowledge/embeddings.py`
- Modify: settings + settings_store + SettingsPatch + `.env.example`
- Modify: retrieve.py / Store（入库后 embed；search 分支）
- Test: `tests/test_knowledge_embeddings.py`（mock OpenAI embeddings.create）

- [ ] **Step 1: Settings 字段**

```python
knowledge_retrieval: Literal["keyword", "vector", "hybrid"] = "keyword"
embedding_api_key: str = ""
embedding_base_url: str = ""
embedding_model: str = ""
```

解析有效凭证：`embedding_api_key or llm_api_key` 等。

- [ ] **Step 2: `embed_texts(texts: list[str]) -> np.ndarray`**；`save_doc_embeddings` / `load_doc_embeddings`

- [ ] **Step 3: create/update 后若有凭证则异步或同步 embed（首版同步）**

- [ ] **Step 4: search**

- `vector` 无凭证 → `ValueError("未配置 embedding")`  
- `hybrid` 无凭证 → keyword + `mode_used=keyword`  
- 有向量：query embed，对所有 doc npy 做余弦相似（文档不多可接受；后续可优化）

- [ ] **Step 5: 单测 mock；PASS**

---

### Task 4: API 路由

**Files:**
- Modify: `apps/api/app/routes/knowledge.py`
- Test: `tests/test_knowledge_api.py`

- [ ] **Step 1: 路由**

```python
GET /docs, GET /docs/{doc_id}?full=0|1
POST /docs, PUT /docs/{doc_id}, DELETE /docs/{doc_id}
POST /docs/upload  # File UploadFile, title Form, tags Form
POST /search  # query, top_k, mode optional
```

Upload：校验后缀与 30MB；pdf → extract；md/txt → decode utf-8；`doc_type` 映射。

- [ ] **Step 2: API 单测**（内存库 + 小 md 上传 + delete + search keyword）

- [ ] **Step 3: 更新 `tests/test_core.py` 知识库用例若破坏**

---

### Task 5: 前端工作台

**Files:**
- Rewrite: `apps/web/src/pages/Knowledge.tsx`

- [ ] **Step 1: UI 结构**

- 顶栏：新建、上传（hidden file input accept=.pdf,.md,.txt）、刷新、次要「示例笔记」  
- 左列文档列表；右列详情/编辑表单  
- 顶部或侧栏搜索框 + 结果列表  

类型：

```ts
type KnowledgeDoc = {
  doc_id: string;
  title: string;
  doc_type: string;
  tags: string;
  chunk_count?: number;
};
```

上传用 `FormData` + `fetch`/`api` 若支持 multipart（检查 `api.ts`；不支持则原生 fetch + token）。

- [ ] **Step 2: 对接 PUT/DELETE/GET detail**

- [ ] **Step 3: 手工验收清单写入计划注释即可**

---

### Task 6: Settings + 投研工具 + 文档收尾

**Files:**
- Settings.tsx：检索模式下拉 + embedding 三字段（可放 LLM Tab 下方「知识库检索」）  
- 确认 `tools.search_knowledge` 仍走 Store.search（传全局 mode）  
- Spec 状态 → 已实现；TODO「进行中」勾掉；保留本地向量 TODO  
- `.env.example` 中文注释同步  

- [x] **Step 1–3: 实现与勾选文档**

---

## Spec coverage

| 规格 | Task |
| --- | --- |
| CRUD 工作台 | 1 + 4 + 5 |
| PDF/md/txt | 1 + 4 |
| keyword/vector/hybrid | 2 + 3 |
| embedding 配置回退 | 3 + 6 |
| search_knowledge | 6 |
| 本地 ST TODO | 已在 TODO.md |
| 30MB / 无 OCR | 4 |

**Placeholder 扫描：** 无 TBD。

---

## 执行方式

Plan complete and saved to `docs/superpowers/plans/2026-07-25-knowledge-workbench.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每 Task 独立子代理 + 复查  
2. **Inline Execution** — 本会话连续实现  

回 `1` 或 `2`。
