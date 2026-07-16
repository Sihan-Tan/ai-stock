import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

/**
 * 展示知识库文档，并上传固定示例笔记。
 * @param props 页面日志写入方法
 */
export default function Knowledge({ setLog }: PageLogProps) {
  const [documents, setDocuments] = useState<unknown[]>([]);

  const upload = async () => {
    try {
      await api("/api/knowledge/docs", { method: "POST", body: JSON.stringify({ title: "半导体景气笔记", tags: "半导体", content: "高位晋级率若连续两日低于 30%，短线情绪退潮概率上升。连板高度与溢价需分开看。" }) });
      setDocuments(await api<unknown[]>("/api/knowledge/docs"));
      setLog("已上传笔记");
    } catch (error) { setLog(String(error)); }
  };

  useEffect(() => { api<unknown[]>("/api/knowledge/docs").then(setDocuments).catch(() => undefined); }, []);

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">知识库</CardTitle><Button variant="primary" onPress={upload}>上传示例笔记</Button></CardHeader>
      <CardContent className="p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(documents, null, 2)}</pre></CardContent>
    </Card>
  );
}
