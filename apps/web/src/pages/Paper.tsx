import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./Overview";

/**
 * 管理模拟账户概览并提交固定示例买单。
 * @param props 页面日志写入方法
 */
export default function Paper({ setLog }: PageLogProps) {
  const [summary, setSummary] = useState<unknown>(null);
  const refresh = () => api("/api/broker/paper").then(setSummary).catch((error) => setLog(String(error)));

  useEffect(() => { refresh(); }, []);

  const buy = async () => {
    try {
      await api("/api/broker/order", { method: "POST", body: JSON.stringify({ symbol: "600519.SH", side: "buy", qty: 100, price: 1680, mode: "paper" }) });
      await refresh();
      setLog("模拟买入完成");
    } catch (error) {
      setLog(String(error));
    }
  };

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">模拟交易</CardTitle><div className="flex gap-2"><Button variant="primary" onPress={buy}>模拟买入 600519</Button><Button variant="secondary" onPress={refresh}>刷新</Button></div></CardHeader>
      <CardContent className="p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(summary, null, 2)}</pre></CardContent>
    </Card>
  );
}
