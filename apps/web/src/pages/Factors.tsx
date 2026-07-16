import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./Overview";

/**
 * 展示因子、模型并触发双引擎对比训练。
 * @param props 页面日志写入方法
 */
export default function Factors({ setLog }: PageLogProps) {
  const [factors, setFactors] = useState<unknown[]>([]);
  const [models, setModels] = useState<unknown[]>([]);
  const [comparison, setComparison] = useState<unknown>(null);

  const refresh = async () => {
    try {
      const [factorRows, modelRows] = await Promise.all([api<unknown[]>("/api/factors"), api<unknown[]>("/api/ml/models")]);
      setFactors(factorRows);
      setModels(modelRows);
    } catch (error) {
      setLog(String(error));
    }
  };

  useEffect(() => { refresh(); }, []);

  const trainBoth = async () => {
    try {
      setComparison(await api("/api/ml/compare-engines", { method: "POST" }));
      await refresh();
      setLog("双引擎对比训练完成");
    } catch (error) {
      setLog(String(error));
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">因子库</CardTitle><div className="flex gap-2"><Button variant="primary" onPress={trainBoth}>LGBM vs XGB 对比训练</Button><Button variant="secondary" onPress={refresh}>刷新</Button></div></CardHeader>
        <CardContent className="p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(factors, null, 2)}</pre></CardContent>
      </Card>
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">模型</CardTitle></CardHeader>
        <CardContent className="space-y-4 p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(models, null, 2)}</pre>{comparison !== null && <><CardTitle className="text-base text-[var(--desk-text)]">引擎对比</CardTitle><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(comparison, null, 2)}</pre></>}</CardContent>
      </Card>
    </div>
  );
}
