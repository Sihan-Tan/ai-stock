import { Button, Card, CardContent } from "@heroui/react";
import { api } from "../api";

export type PageLogProps = {
  setLog: (message: string) => void;
};

/**
 * 展示工作台总览，并提供策略列表同步入口。
 * @param props 页面日志写入方法
 */
export default function Overview({ setLog }: PageLogProps) {
  /**
   * 同步 Python 策略并加载 YAML 策略文件。
   */
  const syncJobs = async () => {
    try {
      await api("/api/strategies/sync-python", { method: "POST" });
      await api("/api/strategies/load-yaml-file", { method: "POST" });
      setLog("已同步策略");
    } catch (error) {
      setLog(String(error));
    }
  };

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardContent className="space-y-4 p-5">
        <p className="text-sm leading-6 text-[var(--desk-mist)]">
          v1 工作台。行情同步请到「行情同步」页触发；策略列表可在此刷新。
        </p>
        <Button variant="primary" onPress={syncJobs}>
          同步策略列表
        </Button>
      </CardContent>
    </Card>
  );
}
