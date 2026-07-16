import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

/**
 * 查看并写入每日盘面复盘。
 * @param props 页面日志写入方法
 */
export default function Review({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<unknown[]>([]);

  const save = async () => {
    try {
      const asof = new Date().toISOString().slice(0, 10);
      await api("/api/review", { method: "POST", body: JSON.stringify({ asof, content: "盘面复盘：情绪与执行偏差备注", deviations: [{ type: "slip" }] }) });
      setRows(await api<unknown[]>("/api/review"));
      setLog("复盘已保存");
    } catch (error) { setLog(String(error)); }
  };

  useEffect(() => { api<unknown[]>("/api/review").then(setRows).catch(() => undefined); }, []);

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">每日复盘</CardTitle><Button variant="primary" onPress={save}>写入今日复盘</Button></CardHeader>
      <CardContent className="p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(rows, null, 2)}</pre></CardContent>
    </Card>
  );
}
