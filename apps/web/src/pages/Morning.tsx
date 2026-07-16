import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./Overview";

/**
 * 执行开盘前及竞价阶段的选拔任务。
 * @param props 页面日志写入方法
 */
export default function Morning({ setLog }: PageLogProps) {
  const [pre, setPre] = useState<unknown>(null);
  const [post, setPost] = useState<unknown>(null);

  const run = async () => {
    try {
      setPre(await api("/api/morning/preopen", { method: "POST" }));
      setPost(await api("/api/morning/post-auction", { method: "POST" }));
    } catch (error) { setLog(String(error)); }
  };

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">晨间选拔</CardTitle><Button variant="primary" onPress={run}>运行开盘前 + 竞价选拔</Button></CardHeader>
      <CardContent className="p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify({ pre, post }, null, 2)}</pre></CardContent>
    </Card>
  );
}
