import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../api";
import { AssistantMessageBody } from "./AssistantMessageBody";
import { buildChatMessages } from "./researchMessages";
import type { PageLogProps } from "./types";

type AiSkill = { name: string; description: string };

type SkillDetail = { name: string; description: string; content: string };

type ChatRole = "user" | "assistant";

type ChatMessage = { role: ChatRole; content: string };

type QuickPrompt = {
  label: string;
  text: string;
  skill_hint?: string;
};

const QUICK_PROMPTS: QuickPrompt[] = [
  {
    label: "五步法 · 茅台",
    text: "帮我用五步法分析贵州茅台 (600519)",
    skill_hint: "write-report",
  },
  {
    label: "财务估值 · 中芯",
    text: "中芯国际 (688981) 最近财务与估值是否合理？",
    skill_hint: "financial-analysis",
  },
  {
    label: "同行对比 · 比亚迪",
    text: "比亚迪 vs 长城汽车横向对比",
    skill_hint: "peer-compare",
  },
  {
    label: "护城河 · 宁德",
    text: "宁德时代护城河与竞争对手",
    skill_hint: "write-report",
  },
];

/** 对话消息区固定高度，避免撑长整页 */
const CHAT_LIST_CLASS =
  "flex h-[min(42vh,380px)] max-h-[380px] min-h-[220px] flex-col gap-3 overflow-y-auto rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4";

/**
 * 投研多轮对话：Skills 勾选、详情弹框与限高对话区。
 * @param props 页面日志写入方法
 */
export default function Research({ setLog }: PageLogProps) {
  const [skills, setSkills] = useState<AiSkill[]>([]);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [skillHint, setSkillHint] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const enabledNames = useMemo(
    () => skills.filter((s) => enabled[s.name] !== false).map((s) => s.name),
    [skills, enabled],
  );

  useEffect(() => {
    api<AiSkill[]>("/api/ai/skills")
      .then((list) => {
        setSkills(list);
        const next: Record<string, boolean> = {};
        for (const s of list) next[s.name] = true;
        setEnabled(next);
      })
      .catch((error) => setLog(String(error)));
    api<{ llm_api_key_set?: boolean }>("/api/settings")
      .then((settings) => setLlmConfigured(Boolean(settings.llm_api_key_set)))
      .catch(() => setLlmConfigured(null));
  }, []);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy]);

  useEffect(() => {
    if (!detail) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setDetail(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [detail]);

  /**
   * 切换 skill 启用状态。
   * @param name skill 名
   * @param on 是否启用
   */
  const toggleSkill = (name: string, on: boolean) => {
    setEnabled((prev) => ({ ...prev, [name]: on }));
    if (!on && skillHint === name) setSkillHint(undefined);
  };

  /**
   * 打开 skill 详情弹框。
   * @param name skill 名
   */
  const openSkillDetail = async (name: string) => {
    setDetailLoading(true);
    try {
      const data = await api<SkillDetail>(`/api/ai/skills/${encodeURIComponent(name)}`);
      setDetail(data);
    } catch (error) {
      setLog(String(error));
    } finally {
      setDetailLoading(false);
    }
  };

  /**
   * 清空对话历史，开始新会话。
   */
  const newSession = () => {
    if (busy) return;
    setMessages([]);
    setDraft("");
    setSkillHint(undefined);
    setLog("已开启新会话");
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  /**
   * 发送用户输入并流式追加助手气泡。
   * @param text 用户文本
   * @param hint 可选 skill 提示
   */
  const send = async (text: string, hint?: string) => {
    const userText = text.trim();
    if (!userText || busy) return;

    const history = messages;
    const apiMessages = buildChatMessages(history, userText);
    let nextHint = hint ?? skillHint;
    const skillsToSend = [...enabledNames];
    if (nextHint && !skillsToSend.includes(nextHint)) {
      skillsToSend.unshift(nextHint);
      setEnabled((prev) => ({ ...prev, [nextHint!]: true }));
    }

    setBusy(true);
    setDraft("");
    setMessages([...history, { role: "user", content: userText }, { role: "assistant", content: "" }]);

    try {
      const body: {
        messages: Array<{ role: string; content: string }>;
        skill_hint?: string;
        enabled_skills: string[];
      } = {
        messages: apiMessages,
        enabled_skills: skillsToSend,
      };
      if (nextHint) body.skill_hint = nextHint;

      const response = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      if (!response.body) {
        throw new Error("响应无流式 body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistant = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        assistant += decoder.decode(value, { stream: true });
        const snapshot = assistant;
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const copy = prev.slice();
          const last = copy[copy.length - 1];
          if (!last || last.role !== "assistant") return prev;
          copy[copy.length - 1] = { role: "assistant", content: snapshot };
          return copy;
        });
      }
      assistant += decoder.decode();
      const finalText = assistant;
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const copy = prev.slice();
        const last = copy[copy.length - 1];
        if (!last || last.role !== "assistant") return prev;
        copy[copy.length - 1] = { role: "assistant", content: finalText || "（无内容）" };
        return copy;
      });
    } catch (error) {
      const err = String(error);
      setLog(err);
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const copy = prev.slice();
        const last = copy[copy.length - 1];
        if (!last || last.role !== "assistant") return prev;
        copy[copy.length - 1] = {
          role: "assistant",
          content: last.content || `请求失败：${err}`,
        };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  };

  /**
   * 填入快捷提示并可直接发送。
   * @param prompt 快捷项
   * @param autoSend 是否立即发送
   */
  const applyQuick = (prompt: QuickPrompt, autoSend = true) => {
    setDraft(prompt.text);
    if (prompt.skill_hint) {
      setSkillHint(prompt.skill_hint);
      setEnabled((prev) => ({ ...prev, [prompt.skill_hint!]: true }));
    }
    if (autoSend) {
      void send(prompt.text, prompt.skill_hint);
    } else {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  /**
   * Ctrl/Cmd + Enter 发送。
   * @param event 键盘事件
   */
  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void send(draft, skillHint);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
      <Card className="h-fit border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-2 p-4 pb-2">
          <CardTitle className="text-base text-[var(--desk-text)]">Skills</CardTitle>
          {llmConfigured === true && (
            <Chip size="sm" variant="soft" color="success">
              LLM 已配置
            </Chip>
          )}
          {llmConfigured === false && (
            <Chip size="sm" variant="soft" color="warning">
              未配置 LLM
            </Chip>
          )}
          {llmConfigured === null && (
            <Chip size="sm" variant="soft" color="accent">
              LLM 状态未知
            </Chip>
          )}
        </CardHeader>
        <CardContent className="space-y-2 p-4 pt-1">
          {llmConfigured === false && (
            <p className="text-xs text-[var(--desk-mist)]">请先到「设置 → LLM」填写 API Key。</p>
          )}
          <p className="text-[11px] text-[var(--desk-mist)]">勾选启用；点名称查看说明</p>
          <ul className="max-h-[min(50vh,420px)] space-y-1 overflow-y-auto">
            {skills.length === 0 && <li className="text-sm text-[var(--desk-mist)]">暂无 skill</li>}
            {skills.map((skill) => {
              const on = enabled[skill.name] !== false;
              return (
                <li
                  key={skill.name}
                  className="flex items-center gap-2 rounded-lg px-1 py-1.5 hover:bg-[var(--desk-ink)]"
                >
                  <input
                    id={`skill-on-${skill.name}`}
                    type="checkbox"
                    className="h-3.5 w-3.5 shrink-0 accent-[var(--desk-accent)]"
                    checked={on}
                    disabled={busy}
                    onChange={(event) => toggleSkill(skill.name, event.target.checked)}
                    aria-label={`启用 ${skill.name}`}
                  />
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left font-mono text-sm text-[var(--desk-text)] underline-offset-2 hover:underline"
                    onClick={() => void openSkillDetail(skill.name)}
                    title="查看详细介绍"
                  >
                    {skill.name}
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="border-t border-[var(--desk-line)] pt-2 text-[11px] text-[var(--desk-mist)]">
            已启用 {enabledNames.length}/{skills.length}
            {skillHint ? ` · 优先 ${skillHint}` : ""}
          </div>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-3 p-4 pb-2">
          <div>
            <CardTitle className="text-base text-[var(--desk-text)]">投研对话</CardTitle>
            <p className="mt-1 text-xs text-[var(--desk-mist)]">基本面 · 同行对比 · 估值 · 五步法</p>
          </div>
          <Button size="sm" variant="secondary" isDisabled={busy} onPress={newSession}>
            新会话
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 p-4 pt-1">
          <div className="flex flex-wrap gap-2">
            {QUICK_PROMPTS.map((prompt) => (
              <Button
                key={prompt.label}
                size="sm"
                variant="secondary"
                isDisabled={busy}
                onPress={() => applyQuick(prompt, true)}
              >
                {prompt.label}
              </Button>
            ))}
          </div>

          <div ref={listRef} className={CHAT_LIST_CLASS}>
            {messages.length === 0 && (
              <div className="m-auto max-w-md px-2 py-8 text-center">
                <p className="text-sm font-medium text-[var(--desk-text)]">从下方输入框开始提问</p>
                <p className="mt-2 text-xs leading-relaxed text-[var(--desk-mist)]">
                  也可点上方快捷提示。支持 Ctrl + Enter 发送。
                </p>
              </div>
            )}
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
          </div>

          <div
            className={[
              "shrink-0 rounded-xl border-2 bg-[var(--desk-ink)] p-3",
              "border-[var(--desk-accent)]/55",
              "focus-within:border-[var(--desk-accent)] focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--desk-accent)_22%,transparent)]",
            ].join(" ")}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <label htmlFor="research-composer" className="text-xs font-medium text-[var(--desk-text)]">
                输入问题
              </label>
              <span className="text-[10px] text-[var(--desk-mist)]">Ctrl + Enter 发送</span>
            </div>
            <textarea
              id="research-composer"
              ref={inputRef}
              aria-label="投研问题"
              rows={3}
              value={draft}
              disabled={busy}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onComposerKeyDown}
              placeholder="例如：帮我用五步法分析贵州茅台 (600519)，并给出估值结论"
              className={[
                "w-full resize-y rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)]",
                "px-3 py-2.5 text-sm leading-relaxed text-[var(--desk-text)]",
                "placeholder:text-[var(--desk-mist)]",
                "outline-none focus:border-[var(--desk-accent)]",
                "disabled:cursor-not-allowed disabled:opacity-60",
                "min-h-[5rem] max-h-[9rem]",
              ].join(" ")}
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] text-[var(--desk-mist)]">
                本次将加载 {enabledNames.length} 个 skill
                {skillHint ? `（优先 ${skillHint}）` : ""}
              </p>
              <Button
                variant="primary"
                isDisabled={busy || !draft.trim()}
                onPress={() => void send(draft, skillHint)}
              >
                {busy ? "生成中…" : "发送"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {(detail || detailLoading) && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
          role="presentation"
          onClick={() => !detailLoading && setDetail(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="skill-detail-title"
            className="max-h-[min(80vh,640px)] w-full max-w-lg overflow-hidden rounded-xl border border-[var(--desk-line)] bg-[var(--desk-panel)] shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-[var(--desk-line)] px-4 py-3">
              <div className="min-w-0">
                <h2 id="skill-detail-title" className="truncate font-mono text-sm text-[var(--desk-text)]">
                  {detail?.name || "加载中…"}
                </h2>
                {detail?.description ? (
                  <p className="mt-1 text-xs text-[var(--desk-mist)]">{detail.description}</p>
                ) : null}
              </div>
              <Button size="sm" variant="ghost" isDisabled={detailLoading} onPress={() => setDetail(null)}>
                关闭
              </Button>
            </div>
            <div className="max-h-[min(60vh,480px)] overflow-y-auto px-4 py-3">
              {detailLoading && !detail ? (
                <p className="text-sm text-[var(--desk-mist)]">正在加载 skill 说明…</p>
              ) : (
                <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-[var(--desk-text)]">
                  {detail?.content || ""}
                </pre>
              )}
            </div>
            {detail && (
              <div className="flex justify-end gap-2 border-t border-[var(--desk-line)] px-4 py-3">
                <Button
                  size="sm"
                  variant="secondary"
                  onPress={() => {
                    toggleSkill(detail.name, true);
                    setSkillHint(detail.name);
                    setDetail(null);
                  }}
                >
                  启用并优先
                </Button>
                <Button size="sm" variant="primary" onPress={() => setDetail(null)}>
                  知道了
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
