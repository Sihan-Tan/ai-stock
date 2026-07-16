import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./Overview";

type WatchlistRow = {
  symbol: string;
  name: string;
  last: string | number;
  pct_chg: string | number;
};

/**
 * 展示行情自选列表，并支持重新拉取最新报价。
 * @param props 页面日志写入方法
 */
export default function Watchlist({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<WatchlistRow[]>([]);

  /**
   * 从 API 拉取当前自选行情。
   */
  const loadWatch = () =>
    api<WatchlistRow[]>("/api/market/watchlist")
      .then(setRows)
      .catch((error) => setLog(String(error)));

  useEffect(() => {
    loadWatch();
  }, []);

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
        <div className="flex items-center gap-3">
          <CardTitle className="text-base text-[var(--desk-text)]">自选行情</CardTitle>
          <Chip variant="soft" color="accent">
            {rows.length} 只
          </Chip>
        </div>
        <Button variant="secondary" onPress={loadWatch}>
          刷新自选
        </Button>
      </CardHeader>
      <CardContent className="p-5 pt-2">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
              <tr>
                <th className="px-3 py-2 font-medium">代码</th>
                <th className="px-3 py-2 font-medium">名称</th>
                <th className="px-3 py-2 font-medium">现价</th>
                <th className="px-3 py-2 font-medium">涨跌</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.symbol}
                  className="border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                >
                  <td className="px-3 py-3 font-mono">{row.symbol}</td>
                  <td className="px-3 py-3">{row.name}</td>
                  <td className="px-3 py-3 font-mono">{row.last}</td>
                  <td className="px-3 py-3 font-mono">{row.pct_chg}</td>
                </tr>
              ))}
              {!rows.length && (
                <tr>
                  <td colSpan={4} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                    暂无自选行情
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
