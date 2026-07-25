import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, beijingToday, formatBeijingTime } from "../api";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";

type ReviewRow = {
  asof?: string;
  content?: string;
  llm?: boolean;
  deviation_count?: number;
};

type ReviewDetail = {
  asof?: string;
  content?: string;
  deviations?: Array<Record<string, unknown>>;
};

type AutoStatus = {
  review_auto?: boolean;
  enabled?: boolean;
  cron?: string;
  last_run?: { at?: string | null; status?: string; message?: string };
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
 * 每日复盘工作台：LLM 生成、手写保存、执行质量与策略归因。
 * @param props 页面日志写入方法
 */
export default function Review({ setLog }: PageLogProps) {
  const [asof, setAsof] = useState(beijingToday());
  const [note, setNote] = useState("");
  const [deviations, setDeviations] = useState<Array<Record<string, unknown>>>([]);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [exec, setExec] = useState<ExecQuality | null>(null);
  const [attr, setAttr] = useState<Attribution | null>(null);
  const [strategies, setStrategies] = useState<StrategyOpt[]>([]);
  const [attrStrategy, setAttrStrategy] = useState<string>("");
  const [auto, setAuto] = useState<AutoStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);

  /**
   * 加载指定日复盘正文。
   * @param day 业务日 YYYY-MM-DD
   */
  const loadDay = async (day: string) => {
    const detail = await api<ReviewDetail>(`/api/review/${encodeURIComponent(day)}`);
    setNote(detail.content || "");
    setDeviations(Array.isArray(detail.deviations) ? detail.deviations : []);
  };

  /**
   * 刷新列表、分析与自动状态。
   */
  const refresh = async () => {
    setBusy(true);
    try {
      const qs = attrStrategy
        ? `?strategy_id=${encodeURIComponent(attrStrategy)}`
        : "";
      const [list, eq, at, st] = await Promise.all([
        api<ReviewRow[]>("/api/review"),
        api<ExecQuality>("/api/review/analytics/execution-quality"),
        api<Attribution>(`/api/review/analytics/attribution${qs}`),
        api<AutoStatus>("/api/review/auto-status").catch(() => null),
      ]);
      setRows(list);
      setExec(eq);
      setAttr(at);
      setAuto(st);
      await loadDay(asof);
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
   * 保存当前日期复盘（保留已有偏差结构，否则写 note 标记）。
   */
  const save = async () => {
    setBusy(true);
    try {
      const payloadDev =
        deviations.length > 0 ? deviations : [{ type: "note", summary: "manual" }];
      await api("/api/review", {
        method: "POST",
        body: JSON.stringify({
          asof,
          content: note,
          deviations: payloadDev,
        }),
      });
      setLog(`复盘已保存 ${asof}`);
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 调用 LLM 生成复盘（覆盖当日）。
   */
  const generate = async () => {
    setGenerating(true);
    try {
      const out = await api<{
        status?: string;
        error?: string;
        reason?: string;
        content?: string;
        deviations?: Array<Record<string, unknown>>;
      }>("/api/review/generate", {
        method: "POST",
        body: JSON.stringify({
          asof,
          strategy_id: attrStrategy || null,
          force: true,
        }),
      });
      if (out.status === "ok") {
        setNote(out.content || "");
        setDeviations(Array.isArray(out.deviations) ? out.deviations : []);
        setLog(`LLM 复盘已生成 ${asof}`);
        await refresh();
      } else if (out.status === "skipped") {
        setLog(`已跳过：${out.reason || "已有笔记"}`);
      } else {
        setLog(out.error || "生成失败");
      }
    } catch (error) {
      setLog(String(error));
    } finally {
      setGenerating(false);
    }
  };

  const autoOn = Boolean(auto?.review_auto ?? auto?.enabled);

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-start justify-between gap-3 p-5 pb-3">
          <div>
            <CardTitle className="text-base text-[var(--desk-text)]">每日复盘</CardTitle>
            <p className="mt-1 text-xs text-[var(--desk-mist)]">
              大盘 · 情绪 · 纸交易执行 · 策略归因；可 LLM 生成或手写保存
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Chip size="sm" variant="soft" className={autoOn ? "text-emerald-600" : ""}>
              自动 {autoOn ? "开" : "关"}
            </Chip>
            <Link
              to="/settings"
              className="text-xs text-[var(--desk-mist)] underline-offset-2 hover:underline"
            >
              设置 REVIEW_AUTO
            </Link>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-[var(--desk-mist)]">
              业务日
              <input
                type="date"
                className="mt-1 block rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2 py-1.5 text-sm text-[var(--desk-text)]"
                value={asof}
                onChange={(e) => {
                  const v = e.target.value;
                  setAsof(v);
                  void loadDay(v).catch((err) => setLog(String(err)));
                }}
              />
            </label>
            <Button
              size="sm"
              variant="primary"
              isDisabled={busy || generating}
              onPress={() => void generate()}
            >
              {generating ? "生成中…" : "LLM 生成复盘"}
            </Button>
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void save()}>
              保存
            </Button>
            <Button size="sm" variant="ghost" isDisabled={busy} onPress={() => void refresh()}>
              刷新
            </Button>
          </div>
          {auto?.cron && (
            <p className="text-xs text-[var(--desk-mist)]">
              定时：{auto.cron}
              {auto.last_run?.at
                ? ` · 最近 ${formatBeijingTime(auto.last_run.at)}（${auto.last_run.status}）`
                : ""}
            </p>
          )}
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="复盘正文（Markdown）。可点「LLM 生成复盘」自动写入大盘/情绪/交易/归因。"
            className="min-h-[220px] w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-3 font-mono text-sm leading-relaxed text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]"
          />
          {deviations.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-[var(--desk-mist)]">结构化偏差</div>
              <ul className="space-y-1.5">
                {deviations.map((d, i) => (
                  <li
                    key={i}
                    className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)]"
                  >
                    <span className="font-mono text-xs text-[var(--desk-mist)]">
                      {String(d.type || "item")}
                      {d.severity ? ` · ${String(d.severity)}` : ""}
                    </span>
                    <div className="mt-0.5">{String(d.summary || JSON.stringify(d))}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="overflow-x-auto max-h-44">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-2 py-2 font-medium">日期</th>
                  <th className="px-2 py-2 font-medium">来源</th>
                  <th className="px-2 py-2 font-medium">摘要</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={`${r.asof}-${i}`}
                    className="cursor-pointer border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]"
                    onClick={() => {
                      if (!r.asof) return;
                      setAsof(r.asof);
                      void loadDay(r.asof).catch((err) => setLog(String(err)));
                    }}
                  >
                    <td className="px-2 py-2 font-mono text-xs">{r.asof || "—"}</td>
                    <td className="px-2 py-2">
                      <Chip size="sm" variant="soft">
                        {r.llm ? "LLM" : "手写"}
                      </Chip>
                    </td>
                    <td className="px-2 py-2 text-[var(--desk-mist)] line-clamp-2">
                      {r.content || "—"}
                    </td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr>
                    <td colSpan={3} className="px-2 py-6 text-center text-[var(--desk-mist)]">
                      暂无复盘
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
          <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
            <div>
              <CardTitle className="text-base text-[var(--desk-text)]">执行质量</CardTitle>
              <p className="mt-1 text-xs text-[var(--desk-mist)]">
                {exec?.message || "纸成交滑点统计"}
              </p>
            </div>
            {exec && (
              <Chip size="sm" variant="soft">
                {exec.trades} 笔
              </Chip>
            )}
          </CardHeader>
          <CardContent className="space-y-4 p-5 pt-2">
            <div className="grid gap-3 sm:grid-cols-2">
              <Metric label="平均滑点" value={fmtBps(exec?.avg_slip_bps)} />
              <Metric
                label="中位 / P95"
                value={`${fmtBps(exec?.median_slip_bps)} / ${fmtBps(exec?.p95_slip_bps)}`}
              />
              <Metric
                label="买 / 卖均滑点"
                value={`${fmtBps(exec?.buy_avg_slip_bps)} / ${fmtBps(exec?.sell_avg_slip_bps)}`}
              />
              <Metric
                label="相对配置"
                value={
                  exec?.slip_vs_config_bps == null
                    ? "—"
                    : `${fmtBps(exec.slip_vs_config_bps)} (配置 ${fmtBps(exec.configured_slip_bps)})`
                }
              />
            </div>
            <div className="overflow-x-auto max-h-48">
              <table className="w-full border-collapse text-left text-sm">
                <thead className="sticky top-0 border-b border-[var(--desk-line)] bg-[var(--desk-panel)] text-[var(--desk-mist)]">
                  <tr>
                    <th className="px-2 py-2 font-medium">时间</th>
                    <th className="px-2 py-2 font-medium">标的</th>
                    <th className="px-2 py-2 font-medium">方向</th>
                    <th className="px-2 py-2 font-medium">滑点</th>
                  </tr>
                </thead>
                <tbody>
                  {(exec?.items || []).slice(0, 20).map((t) => (
                    <tr key={t.id} className="border-b border-[var(--desk-line)] last:border-0">
                      <td className="px-2 py-1.5 font-mono text-xs">
                        {formatBeijingTime(t.created_at)}
                      </td>
                      <td className="px-2 py-1.5 font-mono text-xs">{t.symbol}</td>
                      <td className="px-2 py-1.5">{t.side}</td>
                      <td className="px-2 py-1.5 font-mono">{fmtBps(t.slip_bps ?? null)}</td>
                    </tr>
                  ))}
                  {!exec?.items?.length && (
                    <tr>
                      <td colSpan={4} className="px-2 py-6 text-center text-[var(--desk-mist)]">
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
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Metric
                    label="策略收益"
                    value={fmtPct(attr?.strategy_return)}
                    tone={attr?.strategy_return}
                  />
                  <Metric
                    label="买入持有"
                    value={fmtPct(attr?.buyhold_return)}
                    tone={attr?.buyhold_return}
                  />
                  <Metric
                    label="超额"
                    value={fmtPct(attr?.active_return)}
                    tone={attr?.active_return}
                  />
                  <Metric
                    label="最大回撤"
                    value={fmtPct(attr?.max_drawdown)}
                    tone={attr?.max_drawdown}
                  />
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/**
 * @param n bps 数值
 */
function fmtBps(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(1)}`;
}

/**
 * @param n 小数收益
 */
function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

/**
 * 指标小块。
 */
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
    tone == null || tone === 0 ? "text-[var(--desk-text)]" : chgToneClass(tone);
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2">
      <div className="text-xs text-[var(--desk-mist)]">{label}</div>
      <div className={`mt-1 font-mono text-sm ${color}`}>{value}</div>
    </div>
  );
}
