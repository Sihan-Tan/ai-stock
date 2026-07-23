import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";

type MorningLatest = {
  asof: string;
  briefs: Record<string, { content?: string; stage?: string }>;
  boards: Array<{
    board?: string;
    code?: string;
    name?: string;
    avg_pct?: number;
    count?: number;
    score?: number;
  }>;
  stocks: Array<{
    symbol?: string;
    code?: string;
    name?: string;
    auction_pct?: number;
    auction_amount?: number;
    board?: string;
    score?: number;
  }>;
};

/**
 * 晨会开盘前篇与竞价强势选拔。
 * @param props 页面日志写入方法
 */
export default function Morning({ setLog }: PageLogProps) {
  const [data, setData] = useState<MorningLatest | null>(null);
  const [busy, setBusy] = useState(false);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);

  /**
   * 加载当日晨会结果。
   */
  const load = () =>
    api<MorningLatest>("/api/morning/latest")
      .then(setData)
      .catch((error) => setLog(String(error)));

  useEffect(() => {
    void load();
  }, []);

  /**
   * 运行开盘前 + 竞价选拔。
   */
  const runAll = async () => {
    setBusy(true);
    try {
      await api("/api/morning/preopen", { method: "POST" });
      await api("/api/morning/post-auction", { method: "POST" });
      setLog("晨会开盘前 + 竞价选拔已完成");
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 仅重跑竞价选拔。
   */
  const runAuction = async () => {
    setBusy(true);
    try {
      await api("/api/morning/post-auction", { method: "POST" });
      setLog("竞价选拔已完成");
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 将当日强势个股写入自选。
   */
  const bindWatchlist = async () => {
    setBusy(true);
    try {
      const result = await api<{ count: number; added: string[] }>("/api/morning/bind", {
        method: "POST",
        body: JSON.stringify({ asof: data?.asof || undefined, limit: 20 }),
      });
      setLog(`已写入自选 ${result.count} 只：${(result.added || []).slice(0, 8).join(", ")}`);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  const pre = data?.briefs?.preopen;
  const post = data?.briefs?.post_auction;

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">晨间选拔</CardTitle>
            {data?.asof && (
              <Chip size="sm" variant="soft">
                {data.asof}
              </Chip>
            )}
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              刷新
            </Button>
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void runAuction()}>
              重跑竞价选拔
            </Button>
            <Button
              size="sm"
              variant="secondary"
              isDisabled={busy || !(data?.stocks?.length)}
              onPress={() => void bindWatchlist()}
            >
              一键进自选
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void runAll()}>
              运行开盘前 + 竞价
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 p-5 pt-2 md:grid-cols-2">
          <BriefBlock title="开盘前篇" content={pre?.content} />
          <BriefBlock title="竞价篇" content={post?.content} />
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">强势板块</CardTitle>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-3 py-2 font-medium">板块</th>
                  <th className="px-3 py-2 font-medium">竞价均涨</th>
                  <th className="px-3 py-2 font-medium">成分数</th>
                  <th className="px-3 py-2 font-medium">得分</th>
                </tr>
              </thead>
              <tbody>
                {(data?.boards ?? []).map((board) => (
                  <tr
                    key={board.board || board.code || board.name}
                    className="border-b border-[var(--desk-line)] last:border-0"
                  >
                    <td className="px-3 py-3">{board.board || board.name || board.code || "—"}</td>
                    <td className={`px-3 py-3 font-mono ${chgToneClass(board.avg_pct)}`}>
                      {formatAuctionPct(board.avg_pct)}
                    </td>
                    <td className="px-3 py-3 font-mono">{board.count ?? "—"}</td>
                    <td className="px-3 py-3 font-mono">{formatScore(board.score)}</td>
                  </tr>
                ))}
                {!data?.boards?.length && (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                      暂无强势板块（需先有竞价快照）
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center justify-between gap-2 p-5 pb-3">
          <div>
            <CardTitle className="text-base text-[var(--desk-text)]">强势个股</CardTitle>
            <p className="mt-1 text-xs text-[var(--desk-mist)]">
              「一键进自选」写入监控池，可用策略 Runner 扫描
            </p>
          </div>
          <Button
            size="sm"
            variant="primary"
            isDisabled={busy || !(data?.stocks?.length)}
            onPress={() => void bindWatchlist()}
          >
            一键进自选
          </Button>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-3 py-2 font-medium">代码</th>
                  <th className="px-3 py-2 font-medium">名称</th>
                  <th className="px-3 py-2 font-medium">竞价涨幅</th>
                  <th className="px-3 py-2 font-medium">竞价额</th>
                  <th className="px-3 py-2 font-medium">板块</th>
                  <th className="px-3 py-2 font-medium">得分</th>
                </tr>
              </thead>
              <tbody>
                {(data?.stocks ?? []).map((stock) => {
                  const symbol = stock.symbol || stock.code || "";
                  return (
                    <tr
                      key={symbol}
                      className="cursor-pointer border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                      onClick={() => symbol && setDrawerSymbol(symbol)}
                    >
                      <td className="px-3 py-3 font-mono">{symbol || "—"}</td>
                      <td className="px-3 py-3">{stock.name || "—"}</td>
                      <td className={`px-3 py-3 font-mono ${chgToneClass(stock.auction_pct)}`}>
                        {formatAuctionPct(stock.auction_pct)}
                      </td>
                      <td className="px-3 py-3 font-mono">
                        {formatCompact(stock.auction_amount)}
                      </td>
                      <td className="px-3 py-3">{stock.board || "—"}</td>
                      <td className="px-3 py-3 font-mono">{formatScore(stock.score)}</td>
                    </tr>
                  );
                })}
                {!data?.stocks?.length && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                      暂无强势个股。请先加入自选并在竞价时段运行选拔。
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

/**
 * 晨会文案块。
 * @param props 标题与正文
 */
function BriefBlock({ title, content }: { title: string; content?: string }) {
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4">
      <div className="mb-2 text-sm font-medium text-[var(--desk-text)]">{title}</div>
      <pre className="whitespace-pre-wrap text-xs leading-6 text-[var(--desk-mist)]">
        {content || "暂无内容"}
      </pre>
    </div>
  );
}

/**
 * 竞价涨幅（小数 → 百分数）。
 * @param value 小数涨幅
 */
function formatAuctionPct(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

/**
 * 得分展示。
 * @param value 分数
 */
function formatScore(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

/**
 * 金额缩写。
 * @param value 金额
 */
function formatCompact(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`;
  if (Math.abs(value) >= 10_000) return `${(value / 10_000).toFixed(2)}万`;
  return value.toFixed(0);
}
