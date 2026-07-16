import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./Overview";

/**
 * 查看并控制券商风控开关。
 * @param props 页面日志写入方法
 */
export default function Risk({ setLog }: PageLogProps) {
  const [risk, setRisk] = useState<unknown>(null);
  const [qmt, setQmt] = useState<unknown>(null);

  const load = async () => {
    try {
      const [riskState, qmtState] = await Promise.all([api("/api/broker/risk"), api("/api/broker/qmt/ping")]);
      setRisk(riskState);
      setQmt(qmtState);
    } catch (error) {
      setLog(String(error));
    }
  };

  useEffect(() => { load(); }, []);

  const arm = async () => {
    try {
      setRisk(await api("/api/broker/risk", { method: "POST", body: JSON.stringify({ armed: true, whitelist: ["600519.SH"] }) }));
      setLog("已 ARM（仍需白名单内标的）");
    } catch (error) { setLog(String(error)); }
  };
  const kill = async () => {
    try {
      setRisk(await api("/api/broker/risk", { method: "POST", body: JSON.stringify({ kill_switch: true }) }));
      setLog("Kill Switch 已开启");
    } catch (error) { setLog(String(error)); }
  };

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">风控与 QMT</CardTitle><div className="flex gap-2"><Button variant="primary" onPress={arm}>ARM</Button><Button variant="danger" onPress={kill}>Kill Switch</Button><Button variant="secondary" onPress={load}>刷新</Button></div></CardHeader>
      <CardContent className="p-5 pt-2"><pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify({ qmt, risk }, null, 2)}</pre></CardContent>
    </Card>
  );
}
