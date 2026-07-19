import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../api";
import { buildChatMessages } from "./researchMessages";
import type { PageLogProps } from "./types";

type AiSkill = { name: string; description: string };

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

/**
 * 投研多轮对话：Skills、快捷提示与流式答复。
 * @param props 页面日志写入方法
 */
export default function Research({ setLog }: PageLogProps) {
  const [skills, setSkills] = useState<AiSkill[]>([]);
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [skillHint, setSkillHint] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    api<AiSkill[]>("/api/ai/skills")
      .then(setSkills)
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
    const nextHint = hint ?? skillHint;

    setBusy(true);
    setDraft("");
    setMessages([...history, { role: "user", content: userText }, { role: "assistant", content: "" }]);

    try {
      const body: { messages: Array<{ role: string; content: string }>; skill_hint?: string } = {
        messages: apiMessages,
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
    setSkillHint(prompt.skill_hint);
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
    <div className="grid min-h-[calc(100vh-8rem)] gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <Card className="h-fit border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-2 p-5 pb-3">
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
        <CardContent className="space-y-3 p-5 pt-2">
          {llmConfigured === false && (
            <p className="text-xs text-[var(--desk-mist)]">请先到「设置 → LLM」填写 API Key。</p>
          )}
          <ul className="space-y-1.5">
            {skills.length === 0 && <li className="text-sm text-[var(--desk-mist)]">暂无 skill</li>}
            {skills.map((skill) => {
              const active = skillHint === skill.name;
              return (
                <li key={skill.name}>
                  <button
                    type="button"
                    className={[
                      "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                      active
                        ? "border-[var(--desk-accent)] bg-[var(--desk-ink)]"
                        : "border-transparent hover:border-[var(--desk-line)] hover:bg-[var(--desk-ink)]",
                    ].join(" ")}
                    onClick={() => setSkillHint(skill.name)}
                    title="用作 skill_hint"
                  >
                    <span className="font-mono text-sm text-[var(--desk-text)]">{skill.name}</span>
                    <span className="mt-0.5 block text-xs leading-snug text-[var(--desk-mist)]">
                      {skill.description}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          {skillHint && (
            <div className="flex items-center gap-2 border-t border-[var(--desk-line)] pt-3">
              <Chip size="sm" variant="soft" color="accent">
                hint: {skillHint}
              </Chip>
              <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => setSkillHint(undefined)}>
                清除
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="flex min-h-0 flex-col border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full shrink-0 flex-row flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <div>
            <CardTitle className="text-base text-[var(--desk-text)]">投研对话</CardTitle>
            <p className="mt-1 text-xs text-[var(--desk-mist)]">基本面 · 同行对比 · 估值 · 五步法</p>
          </div>
          <Button size="sm" variant="secondary" isDisabled={busy} onPress={newSession}>
            新会话
          </Button>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3 p-5 pt-2">
          <div className="flex shrink-0 flex-wrap gap-2">
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

          <div
            ref={listRef}
            className="flex min-h-[280px] flex-1 flex-col gap-3 overflow-y-auto rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4"
          >
            {messages.length === 0 && (
              <div className="m-auto max-w-md px-2 py-10 text-center">
                <p className="text-sm font-medium text-[var(--desk-text)]">从下方输入框开始提问</p>
                <p className="mt-2 text-xs leading-relaxed text-[var(--desk-mist)]">
                  也可点上方快捷提示。支持 Ctrl + Enter 发送。
                </p>
              </div>
            )}
            {messages.map((msg, index) => (
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
                <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-[var(--desk-text)]">
                  {msg.content || (busy && index === messages.length - 1 ? "…" : "")}
                </pre>
              </div>
            ))}
          </div>

          {/* 输入区：对比消息区抬高一层，边框与焦点环更明显 */}
          <div
            className={[
              "shrink-0 rounded-xl border-2 bg-[var(--desk-ink)] p-3 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]",
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
              rows={4}
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
                "min-h-[6.5rem]",
              ].join(" ")}
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] text-[var(--desk-mist)]">
                {skillHint ? `将携带 skill：${skillHint}` : "未选择 skill hint（可选左侧列表）"}
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
    </div>
  );
}
