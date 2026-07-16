import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./Overview";

/**
 * 展示告警记录并发送演示告警。
 * @param props 页面日志写入方法
 */
export default function Alerts({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<unknown[]>([]);
  const load = () => api<unknown[]>("/api/alerts").then(setRows).catch((error) => setLog(String(error)));

  useEffect(() => { load(); }, []);

  const send = async () => {
    try {
      await api("/api/alerts/send", { method: "POST", body: JSON.stringify({ title: "演示告警", body: "来自前端", dedupe_key: `ui-${Date.now()}` }) });
      await load();
    } catch (error) { setLog(String(error)); }
  };

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">告警中心</CardTitle><Button variant="primary" onPress={send}>发送演示告警</Button></CardHeader>
      <CardContent className="p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(rows, null, 2)}</pre></CardContent>
    </Card>
  );
}
