import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { detectLimitTag } from "../stock/limitStatus";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";

type WatchBoard = {
  board_code: string;
  board_name: string;
  board_type: string;
  is_primary?: boolean;
};

type WatchlistRow = {
  symbol: string;
  name: string;
  last: number | null;
  pre_close?: number | null;
  pct_chg: number | null;
  change?: number | null;
  volume?: number | null;
  turnover_rate?: number | null;
  boards?: WatchBoard[];
};

/**
 * 展示行情自选列表，并支持重新拉取最新报价。
 * @param props 页面日志写入方法
 */
export default function Watchlist({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<WatchlistRow[]>([]);
  const [watchedMap, setWatchedMap] = useState<Record<string, boolean>>({});
  const [busySymbol, setBusySymbol] = useState<string | null>(null);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);

  /**
   * 从 API 拉取当前自选行情。
   * @param mode full=整表重置；poll=合并价量并保留本地已移出的行
   */
  const loadWatch = (mode: "full" | "poll" = "full") =>
    api<WatchlistRow[]>("/api/market/watchlist")
      .then((data) => {
        if (mode === "full") {
          setRows(data);
          setWatchedMap(Object.fromEntries(data.map((row) => [row.symbol, true])));
          return;
        }
        setRows((prev) => {
          const bySymbol = new Map(data.map((row) => [row.symbol, row]));
          const merged = prev.map((row) => bySymbol.get(row.symbol) ?? row);
          for (const row of data) {
            if (!prev.some((item) => item.symbol === row.symbol)) {
              merged.push(row);
            }
          }
          return merged;
        });
        setWatchedMap((prev) => {
          const next = { ...prev };
          for (const row of data) next[row.symbol] = true;
          return next;
        });
      })
      .catch((error) => setLog(String(error)));

  useEffect(() => {
    void loadWatch("full");
    const timer = window.setInterval(() => {
      void loadWatch("poll");
    }, 15_000);
    return () => window.clearInterval(timer);
  }, []);

  /**
   * 切换标的自选状态；移出后仍保留行便于再加入。
   * @param row 当前行
   */
  const toggleWatch = async (row: WatchlistRow) => {
    if (busySymbol) return;
    const symbol = row.symbol;
    const next = !(watchedMap[symbol] ?? true);
    setBusySymbol(symbol);
    setWatchedMap((prev) => ({ ...prev, [symbol]: next }));
    try {
      if (next) {
        await api("/api/market/watchlist", {
          method: "POST",
          body: JSON.stringify({ symbol, name: row.name || "" }),
        });
      } else {
        await api(`/api/market/watchlist/${encodeURIComponent(symbol)}`, {
          method: "DELETE",
        });
      }
    } catch (error) {
      setWatchedMap((prev) => ({ ...prev, [symbol]: !next }));
      setLog(String(error));
    } finally {
      setBusySymbol(null);
    }
  };

  const watchedCount = rows.filter((row) => watchedMap[row.symbol] ?? true).length;

  return (
    <>
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">自选行情</CardTitle>
            <Chip variant="soft" color="accent">
              {watchedCount} 只
            </Chip>
          </div>
          <Button className="shrink-0" variant="secondary" onPress={() => void loadWatch("full")}>
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
                  <th className="px-3 py-2 font-medium">涨跌幅</th>
                  <th className="px-3 py-2 font-medium">涨跌额</th>
                  <th className="px-3 py-2 font-medium">成交量</th>
                  <th className="px-3 py-2 font-medium">换手率</th>
                  <th className="px-3 py-2 font-medium">板块</th>
                  <th className="px-3 py-2 font-medium">涨跌停</th>
                  <th className="px-3 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const pct = toFiniteNumber(row.pct_chg);
                  const change = toFiniteNumber(row.change);
                  const limitTag = detectLimitTag(row.symbol, row.last, row.pre_close, row.name);
                  const watched = watchedMap[row.symbol] ?? true;
                  return (
                    <tr
                      key={row.symbol}
                      className="cursor-pointer border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                      onClick={() => setDrawerSymbol(row.symbol)}
                    >
                      <td className="px-3 py-3 font-mono">{row.symbol}</td>
                      <td className="px-3 py-3">{row.name || "—"}</td>
                      <td className="px-3 py-3 font-mono">{formatNumber(row.last)}</td>
                      <td className={`px-3 py-3 font-mono ${chgToneClass(pct)}`}>
                        {formatSignedPercent(pct)}
                      </td>
                      <td className={`px-3 py-3 font-mono ${chgToneClass(change)}`}>
                        {formatSigned(change)}
                      </td>
                      <td className="px-3 py-3 font-mono">{formatCompactNumber(row.volume)}</td>
                      <td className="px-3 py-3 font-mono">{formatPercent(row.turnover_rate)}</td>
                      <td className="px-3 py-3">
                        <BoardCell boards={row.boards} />
                      </td>
                      <td className="px-3 py-3">
                        {limitTag === "up" && (
                          <Chip size="sm" color="danger" variant="soft">
                            涨停
                          </Chip>
                        )}
                        {limitTag === "down" && (
                          <Chip size="sm" color="success" variant="soft">
                            跌停
                          </Chip>
                        )}
                        {!limitTag && <span className="text-[var(--desk-mist)]">—</span>}
                      </td>
                      <td
                        className="px-3 py-3"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <Button
                          size="sm"
                          variant={watched ? "ghost" : "secondary"}
                          isDisabled={busySymbol === row.symbol}
                          onPress={() => void toggleWatch(row)}
                        >
                          {watched ? "移出自选" : "加入自选"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
                {!rows.length && (
                  <tr>
                    <td colSpan={10} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                      暂无自选行情
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
    </>
  );
}

/**
 * 展示主行业 / 主概念。
 * @param props.boards 主板块列表
 */
function BoardCell({ boards }: { boards?: WatchBoard[] }) {
  const names = (boards ?? [])
    .filter((board) => board.board_name)
    .map((board) => board.board_name);
  if (!names.length) {
    return <span className="text-[var(--desk-mist)]">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {names.map((name) => (
        <Chip key={name} size="sm" variant="soft">
          {name}
        </Chip>
      ))}
    </div>
  );
}

/**
 * 将未知值解析为有限数字。
 * @param value 原始值
 */
function toFiniteNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/**
 * 格式化价格/数值。
 * @param value 数值
 * @param digits 小数位
 */
function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

/**
 * 格式化带符号数值。
 * @param value 数值
 * @param digits 小数位
 */
function formatSigned(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value).toFixed(digits);
  if (value > 0) return `+${abs}`;
  if (value < 0) return `-${abs}`;
  return abs;
}

/**
 * 格式化带符号涨跌幅。
 * @param value 百分数
 */
function formatSignedPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${formatSigned(value)}%`;
}

/**
 * 格式化百分比。
 * @param value 百分数
 */
function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${formatNumber(value)}%`;
}

/**
 * 成交量等大缩写。
 * @param value 数值
 */
function formatCompactNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`;
  if (Math.abs(value) >= 10_000) return `${(value / 10_000).toFixed(2)}万`;
  return formatNumber(value, 0);
}
