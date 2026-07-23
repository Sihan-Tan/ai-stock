import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";

type LhbSeat = {
  side: string;
  seat_name: string;
  amount: number;
  is_institution?: boolean;
};

type LhbRow = {
  symbol: string;
  name: string;
  reason: string;
  net_buy: number;
  pct_chg?: number | null;
  seats: LhbSeat[];
};

/**
 * 展示同步后的龙虎榜记录。
 * @param props 页面日志写入方法
 */
export default function Lhb({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<LhbRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);

  /**
   * 拉取龙虎榜。
   */
  const load = () =>
    api<LhbRow[]>("/api/lhb")
      .then(setRows)
      .catch((error) => setLog(String(error)));

  useEffect(() => {
    void load();
  }, []);

  /**
   * 触发龙虎榜同步。
   */
  const sync = async () => {
    setBusy(true);
    try {
      const result = await api<{ status?: string; skipped?: boolean }>("/api/lhb/jobs/sync", {
        method: "POST",
      });
      setLog(result.skipped ? "非交易日，已跳过龙虎榜同步" : `龙虎榜同步：${result.status ?? "ok"}`);
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">龙虎榜</CardTitle>
            <Chip variant="soft" color="accent">
              {rows.length} 只
            </Chip>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              刷新
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void sync()}>
              同步龙虎榜
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {!rows.length && (
            <p className="mb-4 text-sm text-[var(--desk-mist)]">
              暂无龙虎榜数据。可点击「同步龙虎榜」从 AkShare 拉取（通常盘后披露）。
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-3 py-2 font-medium">代码</th>
                  <th className="px-3 py-2 font-medium">名称</th>
                  <th className="px-3 py-2 font-medium">涨跌幅</th>
                  <th className="px-3 py-2 font-medium">净买额</th>
                  <th className="px-3 py-2 font-medium">上榜理由</th>
                  <th className="px-3 py-2 font-medium">席位</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.symbol}
                    className="cursor-pointer border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                    onClick={() => setDrawerSymbol(row.symbol)}
                  >
                    <td className="px-3 py-3 font-mono">{row.symbol}</td>
                    <td className="px-3 py-3">{row.name || "—"}</td>
                    <td className={`px-3 py-3 font-mono ${pctClass(row.pct_chg)}`}>
                      {formatSignedPercent(row.pct_chg)}
                    </td>
                    <td className={`px-3 py-3 font-mono ${netClass(row.net_buy)}`}>
                      {formatCompact(row.net_buy)}
                    </td>
                    <td className="max-w-[240px] px-3 py-3 text-[var(--desk-mist)]">{row.reason || "—"}</td>
                    <td className="px-3 py-3 text-[var(--desk-mist)]">
                      {(row.seats || []).length ? `${row.seats.length} 席` : "—"}
                    </td>
                  </tr>
                ))}
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
 * 净买额着色。
 * @param value 净买额
 */
function netClass(value: number | null | undefined): string {
  return chgToneClass(value);
}

/**
 * 涨跌幅着色（A 股习惯：涨红跌绿）。
 * @param value 百分数
 */
function pctClass(value: number | null | undefined): string {
  return chgToneClass(value);
}

/**
 * 格式化带符号涨跌幅。
 * @param value 百分数
 */
function formatSignedPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

/**
 * 金额缩写。
 * @param value 金额
 */
function formatCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(2)}亿`;
  if (abs >= 10_000) return `${sign}${(abs / 10_000).toFixed(2)}万`;
  return `${sign}${abs.toFixed(0)}`;
}
