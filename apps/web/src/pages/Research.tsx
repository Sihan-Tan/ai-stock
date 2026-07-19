import { Button, Card, CardContent, CardHeader, CardTitle, Chip, TextArea } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
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

  /**
   * 清空对话历史，开始新会话。
   */
  const newSession = () => {
    if (busy) return;
    setMessages([]);
    setDraft("");
    setSkillHint(undefined);
    setLog("已开启新会话");
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
    if (autoSend) void send(prompt.text, prompt.skill_hint);
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
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
          <ul className="space-y-2 text-sm text-[var(--desk-mist)]">
            {skills.length === 0 && <li className="text-[var(--desk-mist)]">暂无 skill</li>}
            {skills.map((skill) => (
              <li key={skill.name}>
                <button
                  type="button"
                  className="text-left"
                  onClick={() => setSkillHint(skill.name)}
                  title="用作 skill_hint"
                >
                  <span className="font-mono text-[var(--desk-text)]">{skill.name}</span>
                  <span className="block text-xs">{skill.description}</span>
                </button>
              </li>
            ))}
          </ul>
          {skillHint && (
            <div className="flex items-center gap-2">
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

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">投研对话</CardTitle>
          <Button size="sm" variant="secondary" isDisabled={busy} onPress={newSession}>
            新会话
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 p-5 pt-2">
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

          <div
            ref={listRef}
            className="flex max-h-[min(56vh,520px)] min-h-[240px] flex-col gap-3 overflow-y-auto rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4"
          >
            {messages.length === 0 && (
              <p className="text-sm text-[var(--desk-mist)]">输入问题或点击快捷提示开始多轮投研。</p>
            )}
            {messages.map((msg, index) => (
              <div
                key={`${msg.role}-${index}`}
                className={
                  msg.role === "user"
                    ? "ml-8 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] px-3 py-2"
                    : "mr-4 rounded-lg border border-[var(--desk-line)]/60 bg-transparent px-3 py-2"
                }
              >
                <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--desk-mist)]">
                  {msg.role === "user" ? "你" : "助手"}
                </div>
                <pre className="whitespace-pre-wrap break-words font-sans text-sm text-[var(--desk-text)]">
                  {msg.content || (busy && index === messages.length - 1 ? "…" : "")}
                </pre>
              </div>
            ))}
          </div>

          <TextArea
            aria-label="投研问题"
            value={draft}
            isDisabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="例如：帮我用五步法分析贵州茅台 (600519)"
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="primary"
              isDisabled={busy || !draft.trim()}
              onPress={() => void send(draft, skillHint)}
            >
              {busy ? "生成中…" : "发送"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
