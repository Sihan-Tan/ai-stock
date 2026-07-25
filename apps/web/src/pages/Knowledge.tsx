import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { api, apiFormData } from "../api";
import type { PageLogProps } from "./types";

/** 知识库文档列表项 */
type KnowledgeDoc = {
  doc_id: string;
  title: string;
  doc_type: string;
  tags: string;
  chunk_count?: number;
};

/** 文档详情（含全文） */
type KnowledgeDocDetail = KnowledgeDoc & {
  content?: string;
  content_preview?: string;
  content_truncated?: boolean;
};

/** 检索命中 */
type KnowledgeSearchHit = {
  doc_id: string;
  title: string;
  content?: string;
  score: number;
  chunk_index?: number;
  mode?: string;
};

/** 编辑表单状态 */
type EditorForm = {
  title: string;
  tags: string;
  content: string;
  doc_type: string;
};

const EMPTY_FORM: EditorForm = {
  title: "",
  tags: "",
  content: "",
  doc_type: "markdown",
};

const SAMPLE_NOTE = {
  title: "半导体景气笔记",
  tags: "半导体",
  content:
    "高位晋级率若连续两日低于 30%，短线情绪退潮概率上升。连板高度与溢价需分开看。",
  doc_type: "markdown",
};

const inputClass =
  "w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 将检索正文截断为列表摘要。
 * @param text 原始片段
 * @param maxLen 最大字符数
 */
export function formatSnippet(text: string | undefined, maxLen = 120): string {
  const raw = (text ?? "").replace(/\s+/g, " ").trim();
  if (!raw) return "（无摘要）";
  if (raw.length <= maxLen) return raw;
  return `${raw.slice(0, maxLen)}…`;
}

/**
 * 知识库工作台：列表 / 详情 / 新建 / 编辑 / 删除 / 检索 / 上传。
 * @param props 页面日志写入方法
 */
export default function Knowledge({ setLog }: PageLogProps) {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState<EditorForm>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<KnowledgeSearchHit[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  /**
   * 刷新文档列表。
   */
  const loadDocs = async () => {
    try {
      const rows = await api<KnowledgeDoc[]>("/api/knowledge/docs");
      setDocs(rows);
    } catch (error) {
      setLog(String(error));
    }
  };

  useEffect(() => {
    void loadDocs();
  }, []);

  /**
   * 选中文档并拉取全文到表单。
   * @param docId 文档 ID
   */
  const selectDoc = async (docId: string) => {
    setBusy(true);
    setIsCreating(false);
    try {
      const detail = await api<KnowledgeDocDetail>(
        `/api/knowledge/docs/${encodeURIComponent(docId)}?full=1`,
      );
      setSelectedId(docId);
      setForm({
        title: detail.title || "",
        tags: detail.tags || "",
        content: detail.content ?? detail.content_preview ?? "",
        doc_type: detail.doc_type || "markdown",
      });
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 进入新建空白表单。
   */
  const startCreate = () => {
    setIsCreating(true);
    setSelectedId(null);
    setForm(EMPTY_FORM);
  };

  /**
   * 填入示例笔记到新建表单。
   */
  const fillSample = () => {
    setIsCreating(true);
    setSelectedId(null);
    setForm({ ...SAMPLE_NOTE });
  };

  /**
   * 保存：新建 POST，已有文档 PUT。
   */
  const save = async () => {
    const title = form.title.trim();
    if (!title) {
      setLog("请填写标题");
      return;
    }
    if (!form.content.trim()) {
      setLog("请填写正文");
      return;
    }
    setBusy(true);
    try {
      if (isCreating || !selectedId) {
        const created = await api<KnowledgeDoc>("/api/knowledge/docs", {
          method: "POST",
          body: JSON.stringify({
            title,
            content: form.content,
            tags: form.tags.trim(),
            doc_type: form.doc_type || "markdown",
          }),
        });
        setLog(`已新建：${created.title}`);
        setIsCreating(false);
        setSelectedId(created.doc_id);
        await loadDocs();
      } else {
        await api(`/api/knowledge/docs/${encodeURIComponent(selectedId)}`, {
          method: "PUT",
          body: JSON.stringify({
            title,
            content: form.content,
            tags: form.tags.trim(),
            doc_type: form.doc_type || undefined,
          }),
        });
        setLog(`已保存：${title}`);
        await loadDocs();
      }
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 删除当前文档（需确认）。
   */
  const remove = async () => {
    if (!selectedId || isCreating) return;
    if (!window.confirm(`确定删除「${form.title || selectedId}」？`)) return;
    setBusy(true);
    try {
      await api(`/api/knowledge/docs/${encodeURIComponent(selectedId)}`, {
        method: "DELETE",
      });
      setLog("已删除文档");
      setSelectedId(null);
      setIsCreating(false);
      setForm(EMPTY_FORM);
      await loadDocs();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 上传 PDF / md / txt。
   * @param file 选中的文件
   */
  const uploadFile = async (file: File) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const stem = file.name.replace(/\.[^.]+$/, "");
      if (stem) fd.append("title", stem);
      const created = await apiFormData<KnowledgeDoc>("/api/knowledge/docs/upload", fd);
      setLog(`已上传：${created.title || file.name}`);
      await loadDocs();
      await selectDoc(created.doc_id);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  /**
   * 页内检索。
   */
  const runSearch = async () => {
    const q = searchQuery.trim();
    if (!q) {
      setLog("请输入检索词");
      return;
    }
    setBusy(true);
    try {
      const hits = await api<KnowledgeSearchHit[]>("/api/knowledge/search", {
        method: "POST",
        body: JSON.stringify({ query: q, top_k: 8 }),
      });
      setSearchHits(hits);
      setLog(hits.length ? `检索到 ${hits.length} 条` : "无命中");
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  const editorOpen = isCreating || selectedId != null;

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">知识库</CardTitle>
            <Chip size="sm" variant="soft" color="accent">
              {docs.length} 篇
            </Chip>
          </div>
          <div className="flex flex-wrap shrink-0 gap-2">
            <Button size="sm" variant="primary" isDisabled={busy} onPress={startCreate}>
              新建
            </Button>
            <Button
              size="sm"
              variant="secondary"
              isDisabled={busy}
              onPress={() => fileInputRef.current?.click()}
            >
              上传
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.md,.txt"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void uploadFile(file);
              }}
            />
            <Button
              size="sm"
              variant="secondary"
              isDisabled={busy}
              onPress={() => void loadDocs()}
            >
              刷新
            </Button>
            <Button size="sm" variant="ghost" isDisabled={busy} onPress={fillSample}>
              示例笔记
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-2">
          <div className="flex flex-wrap items-end gap-2">
            <label className="min-w-[12rem] flex-1 space-y-1.5">
              <span className="text-xs text-[var(--desk-mist)]">检索</span>
              <input
                className={inputClass}
                value={searchQuery}
                placeholder="关键词 / 语义查询"
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runSearch();
                }}
              />
            </label>
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void runSearch()}>
              检索
            </Button>
          </div>
          {searchHits.length > 0 ? (
            <ul className="divide-y divide-[var(--desk-line)] rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]">
              {searchHits.map((hit, index) => (
                <li key={`${hit.doc_id}-${hit.chunk_index ?? index}`}>
                  <button
                    type="button"
                    className="flex w-full flex-col gap-1 px-3 py-2.5 text-left hover:bg-[var(--desk-panel)]"
                    onClick={() => void selectDoc(hit.doc_id)}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-[var(--desk-text)]">
                        {hit.title || hit.doc_id}
                      </span>
                      <span className="font-mono text-[11px] text-[var(--desk-mist)]">
                        score {Number(hit.score).toFixed(3)}
                      </span>
                    </div>
                    <p className="text-xs text-[var(--desk-mist)]">
                      {formatSnippet(hit.content)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
        <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
          <CardHeader className="p-5 pb-3">
            <CardTitle className="text-base text-[var(--desk-text)]">文档列表</CardTitle>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            {!docs.length ? (
              <div className="rounded-lg border border-dashed border-[var(--desk-line)] bg-[var(--desk-ink)] px-4 py-8 text-center">
                <p className="text-sm text-[var(--desk-text)]">暂无文档</p>
                <p className="mt-1 text-xs text-[var(--desk-mist)]">
                  点击「新建」或「上传」添加资料。
                </p>
              </div>
            ) : (
              <ul className="max-h-[28rem] space-y-0 divide-y divide-[var(--desk-line)] overflow-y-auto">
                {docs.map((doc) => {
                  const active = !isCreating && selectedId === doc.doc_id;
                  return (
                    <li key={doc.doc_id}>
                      <button
                        type="button"
                        className={`w-full px-2 py-3 text-left transition-colors ${
                          active
                            ? "bg-[var(--desk-ink)]"
                            : "hover:bg-[var(--desk-ink)]/60"
                        }`}
                        onClick={() => void selectDoc(doc.doc_id)}
                      >
                        <div className="truncate text-sm font-medium text-[var(--desk-text)]">
                          {doc.title || "（无标题）"}
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          <Chip size="sm" variant="soft">
                            {doc.doc_type || "note"}
                          </Chip>
                          <span className="text-[11px] text-[var(--desk-mist)]">
                            {doc.chunk_count ?? 0} 切片
                          </span>
                        </div>
                        {doc.tags ? (
                          <p className="mt-1 truncate text-[11px] text-[var(--desk-mist)]">
                            {doc.tags}
                          </p>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
          <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-3 p-5 pb-3">
            <CardTitle className="text-base text-[var(--desk-text)]">
              {isCreating ? "新建文档" : selectedId ? "编辑文档" : "详情"}
            </CardTitle>
            {editorOpen ? (
              <div className="flex shrink-0 gap-2">
                <Button
                  size="sm"
                  variant="primary"
                  isDisabled={busy}
                  onPress={() => void save()}
                >
                  保存
                </Button>
                {!isCreating && selectedId ? (
                  <Button
                    size="sm"
                    variant="danger"
                    isDisabled={busy}
                    onPress={() => void remove()}
                  >
                    删除
                  </Button>
                ) : null}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-3 p-5 pt-2">
            {!editorOpen ? (
              <div className="rounded-lg border border-dashed border-[var(--desk-line)] bg-[var(--desk-ink)] px-4 py-10 text-center">
                <p className="text-sm text-[var(--desk-text)]">未选择文档</p>
                <p className="mt-1 text-xs text-[var(--desk-mist)]">
                  从左侧列表选择，或点击「新建」开始编辑。
                </p>
              </div>
            ) : (
              <>
                <label className="block space-y-1.5">
                  <span className="text-xs text-[var(--desk-mist)]">标题</span>
                  <input
                    className={inputClass}
                    value={form.title}
                    onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
                    placeholder="文档标题"
                  />
                </label>
                <label className="block space-y-1.5">
                  <span className="text-xs text-[var(--desk-mist)]">标签</span>
                  <input
                    className={inputClass}
                    value={form.tags}
                    onChange={(e) => setForm((prev) => ({ ...prev, tags: e.target.value }))}
                    placeholder="逗号或空格分隔"
                  />
                </label>
                <label className="block space-y-1.5">
                  <span className="text-xs text-[var(--desk-mist)]">正文</span>
                  <textarea
                    className={`${inputClass} min-h-[16rem] resize-y font-mono text-xs leading-relaxed`}
                    value={form.content}
                    onChange={(e) => setForm((prev) => ({ ...prev, content: e.target.value }))}
                    placeholder="Markdown / 纯文本"
                  />
                </label>
                {selectedId && !isCreating ? (
                  <p className="text-[11px] text-[var(--desk-mist)]">
                    ID {selectedId} · 类型 {form.doc_type}
                  </p>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
