import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";

type ClosingLatest = {
  asof: string;
  briefs: Record<string, { content?: string; stage?: string }>;
  stocks: Array<{
    symbol?: string;
    code?: string;
    name?: string;
    strategy_id?: string;
    pct_chg?: number;
    score?: number;
  }>;
};

type ClosingStrategy = {
  id: string;
  name: string;
  closing?: boolean;
  status?: string;
};

/**
 * 尾盘选股：策略多选、跑选、文案与命中列表。
 * @param props 页面日志写入方法
 */
export default function Closing({ setLog }: PageLogProps) {
  const [data, setData] = useState<ClosingLatest | null>(null);
  const [strategies, setStrategies] = useState<ClosingStrategy[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);
  const strategiesInitialized = useRef(false);

  /**
   * 加载当日尾盘结果。
   */
  const loadLatest = () =>
    api<ClosingLatest>("/api/closing/latest")
      .then(setData)
      .catch((error) => setLog(String(error)));

  /**
   * 加载策略列表；首次默认勾选 closing 角色策略。
   */
  const loadStrategies = () =>
    api<ClosingStrategy[]>("/api/closing/strategies")
      .then((list) => {
        setStrategies(list);
        if (!strategiesInitialized.current) {
          setSelectedIds(list.filter((item) => item.closing).map((item) => item.id));
          strategiesInitialized.current = true;
        }
      })
      .catch((error) => setLog(String(error)));

  /**
   * 刷新 latest 与策略列表。
   */
  const refresh = async () => {
    await Promise.all([loadLatest(), loadStrategies()]);
  };

  useEffect(() => {
    void refresh();
  }, []);

  /**
   * 切换策略勾选。
   * @param strategyId 策略 ID
   * @param checked 是否选中
   */
  const toggleStrategy = (strategyId: string, checked: boolean) => {
    setSelectedIds((prev) =>
      checked ? [...new Set([...prev, strategyId])] : prev.filter((id) => id !== strategyId)
    );
  };

  /**
   * 立即跑尾盘选股（携带已选策略）。
   */
  const runNow = async () => {
    setBusy(true);
    try {
      await api("/api/closing/run", {
        method: "POST",
        body: JSON.stringify({ strategy_ids: selectedIds }),
      });
      setLog(
        selectedIds.length
          ? `尾盘选股已完成（${selectedIds.length} 个策略）`
          : "尾盘选股已完成（全部 closing 策略）"
      );
      await loadLatest();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 将当日尾盘命中写入自选。
   */
  const bindWatchlist = async () => {
    setBusy(true);
    try {
      const result = await api<{ count: number; added: string[] }>("/api/closing/bind", {
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

  const brief = data?.briefs?.closing;

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">尾盘选股</CardTitle>
            {data?.asof && (
              <Chip size="sm" variant="soft">
                {data.asof}
              </Chip>
            )}
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void refresh()}>
              刷新
            </Button>
            <Button
              size="sm"
              variant="secondary"
              isDisabled={busy || !(data?.stocks?.length)}
              onPress={() => void bindWatchlist()}
            >
              一键进自选
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void runNow()}>
              立即跑
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 p-5 pt-2">
          <BriefBlock title="尾盘篇" content={brief?.content} />
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">策略选择</CardTitle>
          <p className="mt-1 text-xs text-[var(--desk-mist)]">
            默认勾选带 closing 角色的策略；「立即跑」将使用当前勾选列表
          </p>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <div className="flex flex-wrap gap-3">
            {strategies.map((strategy) => (
              <label
                key={strategy.id}
                className="flex items-center gap-2 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)]"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(strategy.id)}
                  onChange={(event) => toggleStrategy(strategy.id, event.target.checked)}
                />
                <span>{strategy.name || strategy.id}</span>
                {strategy.closing && (
                  <Chip size="sm" variant="soft">
                    closing
                  </Chip>
                )}
              </label>
            ))}
            {!strategies.length && (
              <p className="text-sm text-[var(--desk-mist)]">暂无可用策略</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center justify-between gap-2 p-5 pb-3">
          <div>
            <CardTitle className="text-base text-[var(--desk-text)]">命中个股</CardTitle>
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
                  <th className="px-3 py-2 font-medium">策略</th>
                  <th className="px-3 py-2 font-medium">涨跌幅</th>
                  <th className="px-3 py-2 font-medium">score</th>
                </tr>
              </thead>
              <tbody>
                {(data?.stocks ?? []).map((stock) => {
                  const symbol = stock.symbol || stock.code || "";
                  return (
                    <tr
                      key={`${symbol}-${stock.strategy_id || ""}`}
                      className="cursor-pointer border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                      onClick={() => symbol && setDrawerSymbol(symbol)}
                    >
                      <td className="px-3 py-3 font-mono">{symbol || "—"}</td>
                      <td className="px-3 py-3">{stock.name || "—"}</td>
                      <td className="px-3 py-3 font-mono">{stock.strategy_id || "—"}</td>
                      <td className={`px-3 py-3 font-mono ${chgToneClass(stock.pct_chg)}`}>
                        {formatPct(stock.pct_chg)}
                      </td>
                      <td className="px-3 py-3 font-mono">{formatScore(stock.score)}</td>
                    </tr>
                  );
                })}
                {!data?.stocks?.length && (
                  <tr>
                    <td colSpan={5} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                      暂无命中个股。请勾选策略后点击「立即跑」。
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
 * 尾盘文案块。
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
 * 涨跌幅（小数 → 百分数）。
 * @param value 小数涨幅
 */
function formatPct(value: number | undefined): string {
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
