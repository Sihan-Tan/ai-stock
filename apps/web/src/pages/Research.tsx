import { Button, Card, CardContent, CardHeader, CardTitle, TextArea } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

type AiSkill = { name: string; description: string };

/**
 * 展示可用 AI Skills，并发送研究问答请求。
 * @param props 页面日志写入方法
 */
export default function Research({ setLog }: PageLogProps) {
  const [skills, setSkills] = useState<AiSkill[]>([]);
  const [question, setQuestion] = useState("帮我写一个竞价高开策略草稿");
  const [answer, setAnswer] = useState("");

  useEffect(() => {
    api<AiSkill[]>("/api/ai/skills").then(setSkills).catch((error) => setLog(String(error)));
  }, []);

  const send = async () => {
    try {
      const response = await fetch("/api/ai/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: [{ role: "user", content: question }] }) });
      setAnswer(await response.text());
    } catch (error) { setLog(String(error)); }
  };

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">Skills</CardTitle></CardHeader>
        <CardContent className="p-5 pt-2"><ul className="space-y-2 text-sm text-[var(--desk-mist)]">{skills.map((skill) => <li key={skill.name}><span className="font-mono text-[var(--desk-text)]">{skill.name}</span> — {skill.description}</li>)}</ul></CardContent>
      </Card>
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="space-y-3 p-5"><TextArea aria-label="研究问题" value={question} onChange={(event) => setQuestion(event.target.value)} /><Button variant="primary" onPress={send}>发送</Button><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{answer}</pre></CardContent>
      </Card>
    </div>
  );
}
