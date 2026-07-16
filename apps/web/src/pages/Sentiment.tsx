import { Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./Overview";

type SentimentSnapshot = {
  limit_up_count?: number;
  limit_down_count?: number;
  max_board?: number;
  promote_rate?: string | number;
  ladder?: Array<{
    symbol: string;
    board_height: number;
    name: string;
    status: string;
  }>;
};

/**
 * 展示日终市场情绪快照与连板梯队。
 * @param props 页面日志写入方法
 */
export default function Sentiment({ setLog }: PageLogProps) {
  const [data, setData] = useState<SentimentSnapshot | null>(null);

  useEffect(() => {
    api<SentimentSnapshot>("/api/sentiment/snapshot")
      .then(setData)
      .catch((error) => setLog(String(error)));
  }, []);

  if (!data) {
    return (
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="p-5 text-[var(--desk-mist)]">加载中…</CardContent>
      </Card>
    );
  }

  const empty = !data.limit_up_count && !(data.ladder || []).length;

  return (
    <div className="space-y-4">
      {empty && (
        <p className="text-sm text-[var(--desk-mist)]">暂无日终情绪快照。请手动同步：POST /api/sentiment/jobs/sync。</p>
      )}
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="p-5 pb-3">
          <div className="flex flex-wrap gap-2">
            <Chip variant="soft" color="success">涨停 {data.limit_up_count ?? 0}</Chip>
            <Chip variant="soft" color="danger">跌停 {data.limit_down_count ?? 0}</Chip>
            <Chip variant="soft" color="accent">最高 {data.max_board ?? 0} 板</Chip>
            <Chip variant="soft">晋级率 {data.promote_rate ?? "—"}</Chip>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <CardTitle className="mb-3 text-base text-[var(--desk-text)]">连板梯队</CardTitle>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr><th className="px-3 py-2">高度</th><th className="px-3 py-2">代码</th><th className="px-3 py-2">名称</th><th className="px-3 py-2">状态</th></tr>
              </thead>
              <tbody>
                {data.ladder?.map((item) => (
                  <tr key={item.symbol} className="border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]">
                    <td className="px-3 py-3">{item.board_height}</td><td className="px-3 py-3 font-mono">{item.symbol}</td><td className="px-3 py-3">{item.name}</td><td className="px-3 py-3">{item.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
