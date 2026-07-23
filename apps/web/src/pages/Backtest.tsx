import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, beijingToday } from "../api";
import { parseSearchSymbol } from "../stock/parseSearchSymbol";
import { SymbolSearchField } from "../stock/SymbolSearchField";
import { chgToneClass } from "../ui/chgTone";
import { EquityCurveChart } from "./EquityCurveChart";
import type { PageLogProps } from "./types";

type Strategy = {
  id: string;
  name: string;
  status: string;
  source: string;
};

type TradeRow = {
  side?: string;
  /** closed=已平仓；open=期末仍持仓（平仓价为标记市价） */
  status?: "closed" | "open" | string;
  qty?: number;
  entry_price?: number;
  exit_price?: number;
  mark_price?: number;
  pnl?: number;
  pnlcomm?: number;
  return_pct?: number;
  return_pct_gross?: number;
  entry_commission?: number;
  exit_commission?: number;
  stamp_duty?: number;
  fee_total?: number;
  commission?: number;
  dt_open?: string;
  dt_close?: string | null;
};

type BacktestReport = {
  strategy_id: string;
  symbol: string;
  total_return: number;
  max_drawdown: number;
  sharpe: number | null;
  trades: number;
  equity_curve?: Array<{ date?: string; value?: number }>;
  trade_list?: TradeRow[];
};

/**
 * 独立回测工作台：选择策略、参数并查看报告。
 * @param props 页面日志写入方法
 */
export default function Backtest({ setLog }: PageLogProps) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState(searchParams.get("strategy_id") || "");
  const [symbol, setSymbol] = useState("600519.SH");
  const [start, setStart] = useState(defaultStart());
  const [end, setEnd] = useState(defaultEnd());
  const [cash, setCash] = useState("1000000");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(
    () => strategies.find((item) => item.id === strategyId) ?? null,
    [strategies, strategyId]
  );

  useEffect(() => {
    api<Strategy[]>("/api/strategies")
      .then((rows) => {
        setStrategies(rows);
        if (!strategyId && rows[0]) {
          setStrategyId(rows[0].id);
        }
      })
      .catch((err) => setLog(String(err)));
  }, []);

  useEffect(() => {
    const fromQuery = searchParams.get("strategy_id");
    if (fromQuery && fromQuery !== strategyId) {
      setStrategyId(fromQuery);
    }
  }, [searchParams]);

  /**
   * 运行回测。
   */
  const run = async () => {
    if (!strategyId.trim()) {
      setError("请选择策略");
      return;
    }
    const resolvedSymbol = parseSearchSymbol(symbol) ?? symbol.trim().toUpperCase();
    if (!/^\d{6}\.(SH|SZ)$/.test(resolvedSymbol)) {
      setError("请搜索并选择有效标的（代码 / 名称 / 拼音）");
      return;
    }
    setSymbol(resolvedSymbol);
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const body = {
        strategy_id: strategyId.trim(),
        symbol: resolvedSymbol,
        start,
        end,
        initial_cash: Number(cash) || 1_000_000,
      };
      const result = await api<BacktestReport>("/api/backtest/run", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setReport(result);
      setLog(`回测完成：${result.strategy_id} / ${result.symbol}`);
      setSearchParams({ strategy_id: result.strategy_id });
    } catch (err) {
      const message = String(err);
      setError(message);
      setLog(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">回测工作台</CardTitle>
            {selected && (
              <Chip size="sm" variant="soft">
                {selected.source} · {selected.status}
              </Chip>
            )}
          </div>
          <Button size="sm" variant="secondary" onPress={() => navigate("/strategies")}>
            策略管理
          </Button>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Field label="策略">
              <select
                value={strategyId}
                onChange={(event) => {
                  setStrategyId(event.target.value);
                  setSearchParams(
                    event.target.value ? { strategy_id: event.target.value } : {}
                  );
                }}
                className={inputClass}
              >
                {!strategies.length && <option value="">暂无策略</option>}
                {strategies.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id} — {item.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="标的">
              <SymbolSearchField
                value={symbol}
                onChange={setSymbol}
                className={inputClass}
                placeholder="代码 / 名称 / 拼音"
                aria-label="搜索回测标的"
              />
            </Field>
            <Field label="初始资金">
              <input
                value={cash}
                onChange={(event) => setCash(event.target.value)}
                className={inputClass}
                inputMode="decimal"
              />
            </Field>
            <Field label="开始日期">
              <input
                type="date"
                value={start}
                onChange={(event) => setStart(event.target.value)}
                className={inputClass}
              />
            </Field>
            <Field label="结束日期">
              <input
                type="date"
                value={end}
                onChange={(event) => setEnd(event.target.value)}
                className={inputClass}
              />
            </Field>
            <div className="flex items-end">
              <Button
                className="w-full"
                variant="primary"
                isDisabled={busy || !strategyId}
                onPress={() => void run()}
              >
                {busy ? "回测中…" : "运行回测"}
              </Button>
            </div>
          </div>
          {selected?.status === "draft" && (
            <p className="text-xs text-[var(--desk-mist)]">
              当前为草稿策略：允许回测，晋级前请勿用于模拟/实盘。可在{" "}
              <Link className="underline" to="/strategies">
                策略页
              </Link>{" "}
              晋级。
            </p>
          )}
          {error && (
            <div className="rounded-lg border border-[var(--danger)]/40 bg-[var(--danger)]/10 px-4 py-3 text-sm text-[var(--danger)]">
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">回测结果</CardTitle>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {!report && !error && (
            <p className="text-sm text-[var(--desk-mist)]">填写参数后点击「运行回测」。</p>
          )}
          {report && (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric
                  label="总收益"
                  value={formatPct(report.total_return)}
                  tone={report.total_return}
                />
                <Metric
                  label="最大回撤"
                  value={formatPct(report.max_drawdown)}
                  tone={report.max_drawdown}
                />
                <Metric label="夏普" value={report.sharpe == null ? "—" : report.sharpe.toFixed(2)} />
                <Metric
                  label="成交笔数"
                  value={String(
                    report.trade_list?.filter((t) => t.status !== "open").length ??
                      report.trades
                  )}
                />
              </div>
              <p className="text-xs text-[var(--desk-mist)]">
                总收益按期末账户权益（含持仓市值、佣金、印花税、滑点）。明细里「持仓中」行表示回测结束仍持仓，其盈亏为按收盘价估算的浮动盈亏；已平仓的价差盈利若叠加持仓浮动亏损/开仓费用，总收益仍可能为负。
              </p>
              <div className="text-sm text-[var(--desk-mist)]">
                策略 <span className="font-mono text-[var(--desk-text)]">{report.strategy_id}</span>
                {" · "}
                标的 <span className="font-mono text-[var(--desk-text)]">{report.symbol}</span>
              </div>
              {!!report.equity_curve?.length && (
                <div>
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-[var(--desk-text)]">收益曲线</div>
                    <div className="text-xs text-[var(--desk-mist)]">
                      <span className="mr-3 text-[var(--danger)]">▲ 买</span>
                      <span className="text-[var(--success)]">▼ 卖</span>
                      <span className="ml-3">纵轴为累计收益率</span>
                    </div>
                  </div>
                  <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2 py-2">
                    <EquityCurveChart
                      points={report.equity_curve}
                      trades={report.trade_list}
                      height={320}
                    />
                  </div>
                </div>
              )}
              {!!report.trade_list?.length && (
                <div>
                  <div className="mb-2 text-sm font-medium text-[var(--desk-text)]">成交明细</div>
                  <div className="overflow-x-auto max-h-72">
                    <table className="w-full border-collapse text-left text-sm">
                      <thead className="sticky top-0 border-b border-[var(--desk-line)] bg-[var(--desk-panel)] text-[var(--desk-mist)]">
                        <tr>
                          <th className="px-3 py-2 font-medium">开仓</th>
                          <th className="px-3 py-2 font-medium">平仓</th>
                          <th className="px-3 py-2 font-medium">数量</th>
                          <th className="px-3 py-2 font-medium">开仓价</th>
                          <th className="px-3 py-2 font-medium">平仓价</th>
                          <th className="px-3 py-2 font-medium">开仓佣金</th>
                          <th className="px-3 py-2 font-medium">平仓佣金</th>
                          <th className="px-3 py-2 font-medium">印花税</th>
                          <th className="px-3 py-2 font-medium">费用合计</th>
                          <th className="px-3 py-2 font-medium">价差收益</th>
                          <th className="px-3 py-2 font-medium">扣费收益</th>
                          <th className="px-3 py-2 font-medium">盈亏(扣费)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.trade_list.map((t, index) => {
                          const isOpen =
                            t.status === "open" || (t.status == null && !t.dt_close);
                          const notional =
                            t.entry_price != null && t.qty != null ? t.entry_price * t.qty : 0;
                          const grossRet = t.return_pct_gross ?? t.return_pct;
                          const netRet =
                            t.return_pct_gross != null
                              ? t.return_pct
                              : t.pnlcomm != null && notional > 0
                                ? t.pnlcomm / notional
                                : t.return_pct;
                          const markOrExit = t.exit_price ?? t.mark_price;
                          return (
                          <tr
                            key={index}
                            className={`border-b border-[var(--desk-line)] last:border-0 ${
                              isOpen ? "bg-[var(--desk-ink)]/60" : ""
                            }`}
                          >
                            <td className="px-3 py-2 font-mono text-xs">{t.dt_open ?? "—"}</td>
                            <td className="px-3 py-2 font-mono text-xs">
                              {isOpen ? (
                                <span className="text-[var(--warning,#d97706)]">持仓中</span>
                              ) : (
                                t.dt_close ?? "—"
                              )}
                            </td>
                            <td className="px-3 py-2 font-mono">
                              {t.qty != null ? t.qty.toFixed(0) : "—"}
                            </td>
                            <td className="px-3 py-2 font-mono">
                              {t.entry_price != null ? t.entry_price.toFixed(3) : "—"}
                            </td>
                            <td className="px-3 py-2 font-mono">
                              {markOrExit != null
                                ? `${markOrExit.toFixed(3)}${isOpen ? "(市)" : ""}`
                                : "—"}
                            </td>
                            <td className="px-3 py-2 font-mono">
                              {formatMoney(t.entry_commission)}
                            </td>
                            <td className="px-3 py-2 font-mono">
                              {formatMoney(t.exit_commission)}
                            </td>
                            <td className="px-3 py-2 font-mono">{formatMoney(t.stamp_duty)}</td>
                            <td className="px-3 py-2 font-mono">
                              {formatMoney(t.fee_total ?? t.commission)}
                            </td>
                            <td className={`px-3 py-2 font-mono ${chgToneClass(grossRet)}`}>
                              {grossRet != null ? formatPct(grossRet) : "—"}
                            </td>
                            <td className={`px-3 py-2 font-mono ${chgToneClass(netRet)}`}>
                              {netRet != null ? formatPct(netRet) : "—"}
                            </td>
                            <td className={`px-3 py-2 font-mono ${chgToneClass(t.pnlcomm)}`}>
                              {t.pnlcomm != null ? t.pnlcomm.toFixed(2) : "—"}
                            </td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 表单字段包装。
 * @param props 标签与控件
 */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs text-[var(--desk-mist)]">{label}</span>
      {children}
    </label>
  );
}

/**
 * 结果指标块。
 * @param props 文案与数值
 */
function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: number;
}) {
  const color =
    tone == null || tone === 0 ? "text-[var(--desk-text)]" : chgToneClass(tone);
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-4 py-3">
      <div className="text-xs text-[var(--desk-mist)]">{label}</div>
      <div className={`mt-1 font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

/**
 * 小数收益格式化为百分数。
 * @param value 小数
 */
function formatPct(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const pct = value * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

/**
 * 费用金额格式化。
 * @param value 元
 */
function formatMoney(value?: number): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(2);
}

/**
 * 默认回测起始日（约一年前，北京日期）。
 */
function defaultStart(): string {
  const [y, m, d] = beijingToday().split("-");
  return `${Number(y) - 1}-${m}-${d}`;
}

/**
 * 默认回测结束日（北京「今天」）。
 */
function defaultEnd(): string {
  return beijingToday();
}
