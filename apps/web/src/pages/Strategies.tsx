import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

type Strategy = { id: string; version: string; name: string; source: string; status: string };

/**
 * 同步并展示当前策略清单。
 * @param props 页面日志写入方法
 */
export default function Strategies({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<Strategy[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api<Strategy[]>("/api/strategies")
      .then(setRows)
      .catch((error) => setLog(String(error)));

  /**
   * 同步 Python 策略并加载 YAML，再刷新列表。
   */
  const syncJobs = async () => {
    setBusy(true);
    try {
      await api("/api/strategies/sync-python", { method: "POST" });
      await api("/api/strategies/load-yaml-file", { method: "POST" });
      await load();
      setLog("已同步策略");
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center gap-3 p-5 pb-3">
        <CardTitle className="text-base text-[var(--desk-text)]">策略清单</CardTitle>
        <Chip variant="soft" color="accent">
          {rows.length} 个
        </Chip>
        <Button variant="primary" isDisabled={busy} onPress={syncJobs}>
          同步策略列表
        </Button>
      </CardHeader>
      <CardContent className="p-5 pt-2">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
              <tr>
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">名称</th>
                <th className="px-3 py-2">来源</th>
                <th className="px-3 py-2">状态</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={`${row.id}-${row.version}`}
                  className="border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                >
                  <td className="px-3 py-3 font-mono">{row.id}</td>
                  <td className="px-3 py-3">{row.name}</td>
                  <td className="px-3 py-3">{row.source}</td>
                  <td className="px-3 py-3">{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
