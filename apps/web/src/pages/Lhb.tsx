import { Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

/**
 * 展示同步后的龙虎榜原始记录。
 * @param props 页面日志写入方法
 */
export default function Lhb({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<unknown[]>([]);

  useEffect(() => {
    api<unknown[]>("/api/lhb")
      .then(setRows)
      .catch((error) => setLog(String(error)));
  }, []);

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="p-5 pb-3">
        <CardTitle className="text-base text-[var(--desk-text)]">龙虎榜</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-5 pt-2">
        {!rows.length && <p className="text-sm text-[var(--desk-mist)]">暂无龙虎榜数据。请手动同步：POST /api/lhb/jobs/sync。</p>}
        <pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(rows, null, 2)}</pre>
      </CardContent>
    </Card>
  );
}
