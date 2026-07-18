import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { PageLogProps } from "./types";

type Strategy = {
  id: string;
  name: string;
  status: string;
  source: string;
};

type BacktestReport = {
  strategy_id: string;
  symbol: string;
  total_return: number;
  max_drawdown: number;
  sharpe: number | null;
  trades: number;
  equity_curve?: Array<{ value?: number }>;
  trade_list?: unknown[];
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
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const body = {
        strategy_id: strategyId.trim(),
        symbol: symbol.trim().toUpperCase(),
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
              <input
                value={symbol}
                onChange={(event) => setSymbol(event.target.value)}
                className={inputClass}
                placeholder="600519.SH"
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
                <Metric label="成交/信号" value={String(report.trades)} />
              </div>
              <div className="text-sm text-[var(--desk-mist)]">
                策略 <span className="font-mono text-[var(--desk-text)]">{report.strategy_id}</span>
                {" · "}
                标的 <span className="font-mono text-[var(--desk-text)]">{report.symbol}</span>
              </div>
              {!!report.equity_curve?.length && (
                <div>
                  <div className="mb-2 text-sm font-medium text-[var(--desk-text)]">权益摘要</div>
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left text-sm">
                      <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                        <tr>
                          <th className="px-3 py-2 font-medium">#</th>
                          <th className="px-3 py-2 font-medium">权益</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.equity_curve.map((point, index) => (
                          <tr
                            key={index}
                            className="border-b border-[var(--desk-line)] last:border-0"
                          >
                            <td className="px-3 py-3 font-mono">{index + 1}</td>
                            <td className="px-3 py-3 font-mono">
                              {point.value != null ? point.value.toFixed(2) : "—"}
                            </td>
                          </tr>
                        ))}
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
    tone == null || tone === 0
      ? "text-[var(--desk-text)]"
      : tone > 0
        ? "text-[var(--danger)]"
        : "text-[var(--success)]";
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
 * 默认回测起始日（约一年前）。
 */
function defaultStart(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  return toDateInput(d);
}

/**
 * 默认回测结束日（今天）。
 */
function defaultEnd(): string {
  return toDateInput(new Date());
}

/**
 * Date → yyyy-mm-dd。
 * @param value 日期
 */
function toDateInput(value: Date): string {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, "0");
  const d = String(value.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
