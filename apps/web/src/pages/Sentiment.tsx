import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import type { PageLogProps } from "./types";

type SentimentSnapshot = {
  asof?: string;
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
  const [busy, setBusy] = useState(false);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);

  /**
   * 拉取情绪快照。
   */
  const load = () =>
    api<SentimentSnapshot>("/api/sentiment/snapshot")
      .then(setData)
      .catch((error) => setLog(String(error)));

  useEffect(() => {
    void load();
  }, []);

  /**
   * 触发日终情绪同步。
   */
  const sync = async () => {
    setBusy(true);
    try {
      const result = await api<{
        status?: string;
        skipped?: boolean;
        empty_source?: boolean;
        asof?: string;
        cover?: number;
      }>("/api/sentiment/jobs/sync", {
        method: "POST",
      });
      if (result.skipped) {
        setLog("非交易日，已跳过情绪同步");
      } else if (result.empty_source) {
        setLog(
          `情绪同步完成但行情源无涨停表现数据（asof=${result.asof ?? "?"}，cover=${result.cover ?? 0}）。请确认 QMT/xtdata；页面将回退展示库内最近一日。`,
        );
      } else {
        setLog(`情绪同步：${result.status ?? "ok"}（asof=${result.asof ?? "?"}）`);
      }
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  if (!data) {
    return (
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="p-5 text-[var(--desk-mist)]">加载中…</CardContent>
      </Card>
    );
  }

  const empty = !data.limit_up_count && !(data.ladder || []).length;
  const promote =
    typeof data.promote_rate === "number"
      ? `${(data.promote_rate * 100).toFixed(1)}%`
      : data.promote_rate ?? "—";

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <CardTitle className="text-base text-[var(--desk-text)]">打板情绪</CardTitle>
            {data.asof ? (
              <Chip size="sm" variant="soft">
                {data.asof}
              </Chip>
            ) : null}
            <Chip variant="soft" color="danger">
              涨停 {data.limit_up_count ?? 0}
            </Chip>
            <Chip variant="soft" color="success">
              跌停 {data.limit_down_count ?? 0}
            </Chip>
            <Chip variant="soft" color="accent">
              最高 {data.max_board ?? 0} 板
            </Chip>
            <Chip variant="soft">晋级率 {promote}</Chip>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              刷新
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void sync()}>
              同步情绪
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {empty && (
            <p className="mb-4 text-sm text-[var(--desk-mist)]">
              暂无日终情绪快照。可点击「同步情绪」从 QMT 拉取（需交易日与 xtdata 可用）；若库内仅有历史日数据，刷新后会自动展示最近一日。
            </p>
          )}
          <div className="mb-3 text-sm font-medium text-[var(--desk-text)]">连板梯队</div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-3 py-2 font-medium">高度</th>
                  <th className="px-3 py-2 font-medium">代码</th>
                  <th className="px-3 py-2 font-medium">名称</th>
                  <th className="px-3 py-2 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                {data.ladder?.map((item) => (
                  <tr
                    key={item.symbol}
                    className="cursor-pointer border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                    onClick={() => setDrawerSymbol(item.symbol)}
                  >
                    <td className="px-3 py-3">{item.board_height}</td>
                    <td className="px-3 py-3 font-mono">{item.symbol}</td>
                    <td className="px-3 py-3">{item.name}</td>
                    <td className="px-3 py-3">{item.status === "sealed" ? "封板" : item.status === "broken" ? "破板" : item.status}</td>
                  </tr>
                ))}
                {!data.ladder?.length && (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                      暂无梯队数据
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <StockDetailDrawer
        open={drawerSymbol !== null}
        symbol={drawerSymbol ?? ""}
        onClose={() => setDrawerSymbol(null)}
      />
    </div>
  );
}
