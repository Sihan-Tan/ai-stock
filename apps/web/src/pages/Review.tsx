import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api, beijingToday, formatBeijingTime } from "../api";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";

type ReviewRow = {
  asof?: string;
  content?: string;
  deviations?: unknown;
};

type ExecQuality = {
  trades: number;
  with_bar: number;
  avg_slip_bps: number | null;
  median_slip_bps: number | null;
  p95_slip_bps: number | null;
  buy_avg_slip_bps: number | null;
  sell_avg_slip_bps: number | null;
  configured_slip_bps: number;
  slip_vs_config_bps: number | null;
  buy_count: number;
  sell_count: number;
  total_notional: number;
  message?: string;
  items?: Array<{
    id?: number;
    symbol?: string;
    side?: string;
    qty?: number;
    price?: number;
    close?: number | null;
    slip_bps?: number | null;
    created_at?: string | null;
  }>;
};

type Attribution = {
  status: string;
  message?: string;
  strategy_id?: string;
  symbol?: string;
  start_date?: string | null;
  end_date?: string | null;
  strategy_return?: number;
  buyhold_return?: number | null;
  buyhold_source?: string;
  active_return?: number | null;
  max_drawdown?: number;
  sharpe?: number | null;
  closed_trades?: number;
  open_positions?: number;
  win_rate?: number | null;
  pnl_gross?: number | null;
  pnl_net?: number | null;
  fee_total?: number;
  fee_drag?: number | null;
};

type StrategyOpt = { id: string; name: string };

/**
 * 每日复盘 + 执行质量 + 策略归因。
 * @param props 页面日志写入方法
 */
export default function Review({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [exec, setExec] = useState<ExecQuality | null>(null);
  const [attr, setAttr] = useState<Attribution | null>(null);
  const [strategies, setStrategies] = useState<StrategyOpt[]>([]);
  const [attrStrategy, setAttrStrategy] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("盘面复盘：情绪与执行偏差备注");

  /**
   * 刷新复盘列表、执行质量与归因。
   */
  const refresh = async () => {
    setBusy(true);
    try {
      const qs = attrStrategy
        ? `?strategy_id=${encodeURIComponent(attrStrategy)}`
        : "";
      const [list, eq, at] = await Promise.all([
        api<ReviewRow[]>("/api/review"),
        api<ExecQuality>("/api/review/analytics/execution-quality"),
        api<Attribution>(`/api/review/analytics/attribution${qs}`),
      ]);
      setRows(list);
      setExec(eq);
      setAttr(at);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void api<StrategyOpt[]>("/api/strategies")
      .then((list) => setStrategies(list.map((s) => ({ id: s.id, name: s.name }))))
      .catch(() => undefined);
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 写入今日复盘笔记。
   */
  const save = async () => {
    setBusy(true);
    try {
      const asof = beijingToday();
      await api("/api/review", {
        method: "POST",
        body: JSON.stringify({
          asof,
          content: note,
          deviations: [{ type: "note" }],
        }),
      });
      setLog("复盘已保存");
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">每日复盘</CardTitle>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void refresh()}>
              刷新分析
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void save()}>
              写入今日复盘
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-2">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="min-h-[88px] w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-3 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]"
          />
          <div className="overflow-x-auto max-h-48">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-2 py-2 font-medium">日期</th>
                  <th className="px-2 py-2 font-medium">内容</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.asof}-${i}`} className="border-b border-[var(--desk-line)] last:border-0">
                    <td className="px-2 py-2 font-mono text-xs">{r.asof || "—"}</td>
                    <td className="px-2 py-2 text-[var(--desk-mist)]">{r.content || "—"}</td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr>
                    <td colSpan={2} className="px-2 py-6 text-center text-[var(--desk-mist)]">
                      暂无复盘
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <div>
            <CardTitle className="text-base text-[var(--desk-text)]">执行质量</CardTitle>
            <p className="mt-1 text-xs text-[var(--desk-mist)]">{exec?.message || "纸成交滑点统计"}</p>
          </div>
          {exec && (
            <Chip size="sm" variant="soft">
              {exec.trades} 笔
            </Chip>
          )}
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="平均滑点" value={fmtBps(exec?.avg_slip_bps)} />
            <Metric label="中位 / P95" value={`${fmtBps(exec?.median_slip_bps)} / ${fmtBps(exec?.p95_slip_bps)}`} />
            <Metric label="买 / 卖均滑点" value={`${fmtBps(exec?.buy_avg_slip_bps)} / ${fmtBps(exec?.sell_avg_slip_bps)}`} />
            <Metric
              label="相对配置"
              value={
                exec?.slip_vs_config_bps == null
                  ? "—"
                  : `${fmtBps(exec.slip_vs_config_bps)} (配置 ${fmtBps(exec.configured_slip_bps)})`
              }
            />
          </div>
          <div className="text-xs text-[var(--desk-mist)]">
            买 {exec?.buy_count ?? 0} · 卖 {exec?.sell_count ?? 0} · 有日线对照{" "}
            {exec?.with_bar ?? 0} · 成交额{" "}
            {(exec?.total_notional ?? 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 })}
          </div>
          <div className="overflow-x-auto max-h-56">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="sticky top-0 border-b border-[var(--desk-line)] bg-[var(--desk-panel)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-2 py-2 font-medium">时间</th>
                  <th className="px-2 py-2 font-medium">标的</th>
                  <th className="px-2 py-2 font-medium">方向</th>
                  <th className="px-2 py-2 font-medium">成交价</th>
                  <th className="px-2 py-2 font-medium">收盘</th>
                  <th className="px-2 py-2 font-medium">滑点 bps</th>
                </tr>
              </thead>
              <tbody>
                {(exec?.items || []).slice(0, 40).map((t) => (
                  <tr key={t.id} className="border-b border-[var(--desk-line)] last:border-0">
                    <td className="px-2 py-1.5 font-mono text-xs">
                      {formatBeijingTime(t.created_at)}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-xs">{t.symbol}</td>
                    <td className="px-2 py-1.5">{t.side}</td>
                    <td className="px-2 py-1.5 font-mono">{t.price?.toFixed(3) ?? "—"}</td>
                    <td className="px-2 py-1.5 font-mono">{t.close != null ? t.close.toFixed(3) : "—"}</td>
                    <td className="px-2 py-1.5 font-mono">{fmtBps(t.slip_bps ?? null)}</td>
                  </tr>
                ))}
                {!exec?.items?.length && (
                  <tr>
                    <td colSpan={6} className="px-2 py-6 text-center text-[var(--desk-mist)]">
                      暂无纸成交
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <div>
            <CardTitle className="text-base text-[var(--desk-text)]">策略归因</CardTitle>
            <p className="mt-1 text-xs text-[var(--desk-mist)]">
              {attr?.message || "策略收益 vs 同期买入持有"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2 py-1.5 text-xs text-[var(--desk-text)]"
              value={attrStrategy}
              onChange={(e) => setAttrStrategy(e.target.value)}
            >
              <option value="">最近一次回测</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.id})
                </option>
              ))}
            </select>
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void refresh()}>
              分析
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {attr?.status === "empty" ? (
            <p className="text-sm text-[var(--desk-mist)]">{attr.message}</p>
          ) : (
            <>
              <div className="mb-3 text-xs text-[var(--desk-mist)]">
                {attr?.strategy_id} · {attr?.symbol} · {attr?.start_date} → {attr?.end_date}
                {attr?.buyhold_source ? ` · BH来源 ${attr.buyhold_source}` : ""}
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="策略收益" value={fmtPct(attr?.strategy_return)} tone={attr?.strategy_return} />
                <Metric label="买入持有" value={fmtPct(attr?.buyhold_return)} tone={attr?.buyhold_return} />
                <Metric label="超额 (active)" value={fmtPct(attr?.active_return)} tone={attr?.active_return} />
                <Metric label="最大回撤" value={fmtPct(attr?.max_drawdown)} tone={attr?.max_drawdown} />
                <Metric label="夏普" value={attr?.sharpe == null ? "—" : attr.sharpe.toFixed(2)} />
                <Metric label="胜率" value={attr?.win_rate == null ? "—" : fmtPct(attr.win_rate)} />
                <Metric label="费用合计" value={attr?.fee_total == null ? "—" : attr.fee_total.toFixed(2)} />
                <Metric label="费用拖累" value={attr?.fee_drag == null ? "—" : attr.fee_drag.toFixed(2)} />
              </div>
              <p className="mt-3 text-xs text-[var(--desk-mist)]">
                已平仓 {attr?.closed_trades ?? 0} · 持仓中 {attr?.open_positions ?? 0} · 价差盈亏{" "}
                {attr?.pnl_gross == null ? "—" : attr.pnl_gross.toFixed(2)} · 扣费盈亏{" "}
                {attr?.pnl_net == null ? "—" : attr.pnl_net.toFixed(2)}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function fmtBps(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(1)}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: number | null;
}) {
  const color =
    tone == null || tone === 0
      ? "text-[var(--desk-text)]"
      : chgToneClass(tone);
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2">
      <div className="text-xs text-[var(--desk-mist)]">{label}</div>
      <div className={`mt-1 font-mono text-sm ${color}`}>{value}</div>
    </div>
  );
}
