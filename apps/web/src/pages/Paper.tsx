import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Chip,
  Input,
} from "@heroui/react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import type { PositionContext } from "../stock/types";
import type { PageLogProps } from "./types";

type PaperPosition = { symbol: string; qty: number; cost: number };
type PaperTrade = {
  id: number;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  created_at: string | null;
};
type PaperSummary = {
  cash: number;
  equity: number;
  initial_cash?: number;
  updated_at?: string | null;
  positions: PaperPosition[];
  trades?: PaperTrade[];
};
type WatchRow = { symbol: string; name?: string; last?: number; pct_chg?: number };
type AlertRow = { id?: number; title?: string; body?: string; category?: string; created_at?: string };
type RiskState = {
  armed?: boolean;
  kill_switch?: boolean;
  max_order_position_pct?: number;
  max_order_notional?: number;
  max_daily_notional?: number;
  whitelist?: string[];
};

type ModeTab = "monitor" | "live";
type DrawerState = { symbol: string; position: PositionContext };
type StrategyOpt = { id: string; name: string };
type ApprovalItem = {
  id?: number;
  client_order_id: string;
  symbol: string;
  side: string;
  qty: number;
  price?: number | null;
  status?: string;
  message?: string;
  created_at?: string | null;
};
type TradingModeState = {
  trade_mode?: string;
  auto_execute_live?: boolean;
  i_understand_auto_live?: boolean;
  live_execution?: string;
};

const selectClass =
  "rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2 py-1.5 text-xs text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 实盘监控仪表盘：持仓 / 信号 / 资金 / 成交 / 风控说明。
 * @param props 页面日志写入方法
 */
export default function Paper({ setLog }: PageLogProps) {
  const [tab, setTab] = useState<ModeTab>("monitor");
  const [summary, setSummary] = useState<PaperSummary | null>(null);
  const [watch, setWatch] = useState<WatchRow[]>([]);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [risk, setRisk] = useState<RiskState | null>(null);
  const [running, setRunning] = useState(true);
  const [addSymbol, setAddSymbol] = useState("");
  const [busy, setBusy] = useState(false);
  const [openPanel, setOpenPanel] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [strategies, setStrategies] = useState<StrategyOpt[]>([]);
  const [runStrategyId, setRunStrategyId] = useState("ma_cross");
  const [runSymbol, setRunSymbol] = useState("600519.SH");
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [tradingMode, setTradingMode] = useState<TradingModeState | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [paper, wl, al, rk, ap, tm] = await Promise.all([
        api<PaperSummary>("/api/broker/paper"),
        api<WatchRow[]>("/api/market/watchlist").catch(() => [] as WatchRow[]),
        api<AlertRow[]>("/api/alerts").catch(() => [] as AlertRow[]),
        api<RiskState>("/api/broker/risk").catch(() => null),
        api<{ items: ApprovalItem[] }>("/api/broker/approvals").catch(() => ({ items: [] })),
        api<TradingModeState>("/api/broker/trading-mode").catch(() => null),
      ]);
      setSummary(paper);
      setWatch(wl);
      setAlerts(al);
      setRisk(rk);
      setApprovals(ap.items || []);
      setTradingMode(tm);
    } catch (error) {
      setLog(String(error));
    }
  }, [setLog]);

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 15000);
    return () => window.clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    void api<StrategyOpt[]>("/api/strategies")
      .then((list) => {
        setStrategies(list.map((s) => ({ id: s.id, name: s.name })));
        if (list[0] && !list.some((s) => s.id === runStrategyId)) {
          setRunStrategyId(list[0].id);
        }
      })
      .catch(() => undefined);
    // 仅挂载时拉取策略列表
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 对指定标的跑一次纸交易策略。
   */
  const runPaperOnce = async () => {
    const symbol = runSymbol.trim().toUpperCase();
    if (!symbol || !runStrategyId) return;
    setBusy(true);
    try {
      const result = await api<{
        status: string;
        message?: string;
        signals?: unknown[];
        orders?: Array<{ status?: string; message?: string }>;
        last_price?: number;
      }>("/api/broker/paper/run-once", {
        method: "POST",
        body: JSON.stringify({ strategy_id: runStrategyId, symbol }),
      });
      const nOrd = result.orders?.length ?? 0;
      const nSig = result.signals?.length ?? 0;
      setLog(
        result.status === "ok"
          ? `Runner ${runStrategyId}@${symbol}: 信号 ${nSig} · 订单 ${nOrd}` +
              (result.orders?.[0]?.status ? ` · ${result.orders[0].status}` : "") +
              (result.last_price != null ? ` · 价 ${result.last_price}` : "")
          : `Runner 失败: ${result.message || result.status}`
      );
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 对自选全部标的跑一次纸交易策略。
   */
  const runPaperWatchlist = async () => {
    if (!runStrategyId) return;
    setBusy(true);
    try {
      const result = await api<{
        status: string;
        count: number;
        filled: number;
      }>("/api/broker/paper/run-watchlist", {
        method: "POST",
        body: JSON.stringify({ strategy_id: runStrategyId }),
      });
      setLog(
        `Runner 自选: ${runStrategyId} · 扫描 ${result.count} · 成交 ${result.filled}`
      );
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  const quoteMap = useMemo(() => {
    const m = new Map<string, WatchRow>();
    for (const row of watch) m.set(row.symbol, row);
    return m;
  }, [watch]);

  const positions = useMemo(() => {
    const rows = (summary?.positions || []).map((p) => {
      const q = quoteMap.get(p.symbol);
      const last = Number(q?.last ?? p.cost);
      const mv = p.qty * last;
      const pnl = (last - p.cost) * p.qty;
      const pnlPct = p.cost > 0 ? ((last - p.cost) / p.cost) * 100 : 0;
      return {
        ...p,
        name: q?.name || p.symbol,
        strategy: "默认策略",
        last,
        mv,
        pnl,
        pnlPct,
        pending: p.qty <= 0,
      };
    });
    return rows;
  }, [summary, quoteMap]);

  const heldCount = positions.filter((p) => p.qty > 0).length;
  const pendingCount = positions.filter((p) => p.qty <= 0).length;

  const initialCash = summary?.initial_cash ?? 1_000_000;
  const cash = summary?.cash ?? 0;
  const posMv = positions.reduce((s, p) => s + p.mv, 0);
  const totalEquity = cash + posMv;
  const pnlVsInit = totalEquity - initialCash;
  const pnlVsInitPct = initialCash > 0 ? (pnlVsInit / initialCash) * 100 : 0;

  const trades = summary?.trades || [];
  const signalAlerts = alerts.filter((a) => (a.category || "").includes("signal") || true).slice(0, 30);

  /**
   * 添加标的：写入自选并尝试小额示例买入建仓。
   */
  const addStock = async () => {
    const symbol = addSymbol.trim().toUpperCase();
    if (!symbol) return;
    setBusy(true);
    try {
      await api("/api/market/watchlist", {
        method: "POST",
        body: JSON.stringify({ symbol, name: symbol }),
      });
      const snap = await api<Record<string, { last?: number }>>(
        `/api/market/intraday/quote?symbols=${encodeURIComponent(symbol)}`
      ).catch(() => ({} as Record<string, { last?: number }>));
      const price = Number(snap[symbol]?.last || 10);
      await api("/api/broker/order", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          side: "buy",
          qty: 100,
          price,
          mode: "paper",
        }),
      });
      setAddSymbol("");
      setLog(`已添加并建仓 ${symbol}`);
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  const resetPaper = async () => {
    setBusy(true);
    try {
      setSummary(await api<PaperSummary>("/api/broker/paper/reset", { method: "POST" }));
      setLog("已重置持仓与流水");
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 批准待审批实盘单。
   */
  const approveOrder = async (clientOrderId: string) => {
    setBusy(true);
    try {
      const r = await api<{ status: string; message?: string }>(
        `/api/broker/approvals/${encodeURIComponent(clientOrderId)}/approve`,
        { method: "POST" }
      );
      setLog(`已批准 ${clientOrderId}: ${r.status} ${r.message || ""}`);
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 拒绝待审批实盘单。
   */
  const rejectOrder = async (clientOrderId: string) => {
    setBusy(true);
    try {
      await api(`/api/broker/approvals/${encodeURIComponent(clientOrderId)}/reject`, {
        method: "POST",
      });
      setLog(`已拒绝 ${clientOrderId}`);
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  const nowLabel = new Date().toLocaleTimeString("zh-CN", { hour12: false });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] p-1">
          <button
            type="button"
            className={[
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab === "monitor"
                ? "bg-[var(--desk-accent)] font-semibold text-[var(--desk-panel)]"
                : "text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
            ].join(" ")}
            onClick={() => setTab("monitor")}
          >
            模拟盘
          </button>
          <button
            type="button"
            className={[
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab === "live"
                ? "bg-[var(--desk-accent)] font-semibold text-[var(--desk-panel)]"
                : "text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
            ].join(" ")}
            onClick={() => setTab("live")}
          >
            实盘
          </button>
        </div>
        <p className="text-xs text-[var(--desk-mist)]">
          {tab === "monitor"
            ? "纸交易监控：用「策略 Runner」评估信号并下模拟单，不会真实下单"
            : "实盘 (/live)：需 ARM + 白名单，真实通道下单"}
        </p>
      </div>

      {tab === "live" ? (
        <div className="space-y-4">
          <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
            <CardHeader className="p-5 pb-2">
              <CardTitle className="text-base">实盘通道</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 p-5 pt-2 text-sm text-[var(--desk-mist)]">
              <p>
                实盘下单受风控闸门约束。armed=
                <span className="font-mono text-[var(--desk-text)]">
                  {String(risk?.armed ?? false)}
                </span>
                ，kill=
                <span className="font-mono text-[var(--desk-text)]">
                  {String(risk?.kill_switch ?? false)}
                </span>
                。执行模式=
                <span className="font-mono text-[var(--desk-text)]">
                  {tradingMode?.live_execution || "—"}
                </span>
                （自动={String(tradingMode?.auto_execute_live ?? false)} / 确认=
                {String(tradingMode?.i_understand_auto_live ?? false)}）。可在「设置」改双开关。
              </p>
              <Button variant="secondary" onPress={refresh}>
                刷新状态
              </Button>
            </CardContent>
          </Card>

          <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
            <CardHeader className="flex flex-wrap items-center justify-between gap-2 p-5 pb-2">
              <div>
                <CardTitle className="text-base">待审批订单</CardTitle>
                <p className="mt-1 text-xs text-[var(--desk-mist)]">
                  live 且未开自动成交时，订单进入此队列
                </p>
              </div>
              <Chip size="sm" variant="soft">
                {approvals.length} 笔
              </Chip>
            </CardHeader>
            <CardContent className="p-5 pt-2">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm">
                  <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                    <tr>
                      <th className="px-2 py-2 font-medium">时间</th>
                      <th className="px-2 py-2 font-medium">标的</th>
                      <th className="px-2 py-2 font-medium">方向</th>
                      <th className="px-2 py-2 font-medium">数量</th>
                      <th className="px-2 py-2 font-medium">价格</th>
                      <th className="px-2 py-2 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {approvals.map((a) => (
                      <tr
                        key={a.client_order_id}
                        className="border-b border-[var(--desk-line)] last:border-0"
                      >
                        <td className="px-2 py-2 font-mono text-xs">
                          {a.created_at?.slice(0, 19) || "—"}
                        </td>
                        <td className="px-2 py-2 font-mono text-xs">{a.symbol}</td>
                        <td className="px-2 py-2">{a.side}</td>
                        <td className="px-2 py-2 font-mono">{a.qty}</td>
                        <td className="px-2 py-2 font-mono">
                          {a.price != null ? a.price.toFixed(3) : "—"}
                        </td>
                        <td className="px-2 py-2">
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              variant="primary"
                              isDisabled={busy}
                              onPress={() => void approveOrder(a.client_order_id)}
                            >
                              批准
                            </Button>
                            <Button
                              size="sm"
                              variant="danger"
                              isDisabled={busy}
                              onPress={() => void rejectOrder(a.client_order_id)}
                            >
                              拒绝
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!approvals.length && (
                      <tr>
                        <td colSpan={6} className="px-2 py-8 text-center text-[var(--desk-mist)]">
                          暂无待审批订单
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,1fr)]">
          {/* 左栏 */}
          <div className="space-y-4">
            <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
              <CardHeader className="flex flex-wrap items-start justify-between gap-3 p-5 pb-3">
                <div>
                  <CardTitle className="text-base text-[var(--desk-text)]">实时持仓</CardTitle>
                  <p className="mt-1 text-xs text-[var(--desk-mist)]">
                    {heldCount} 只持仓 · {pendingCount} 只待入场 · 点策略名可切换
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    aria-label="添加股票代码"
                    className="w-36"
                    placeholder="600519.SH"
                    value={addSymbol}
                    onChange={(e) => setAddSymbol(e.target.value)}
                  />
                  <Button variant="primary" isDisabled={busy} onPress={addStock}>
                    + 添加股票
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-5 pt-0">
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left text-sm">
                    <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                      <tr>
                        {[
                          "代码",
                          "名称",
                          "执行策略",
                          "持仓",
                          "成本",
                          "现价",
                          "市值",
                          "浮盈/亏",
                          "盈亏%",
                        ].map((h) => (
                          <th key={h} className="px-2 py-2 font-medium">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {positions.length === 0 && (
                        <tr>
                          <td colSpan={9} className="px-2 py-8 text-center text-[var(--desk-mist)]">
                            暂无持仓，点击「添加股票」建仓
                          </td>
                        </tr>
                      )}
                      {positions.map((p) => (
                        <tr
                          key={p.symbol}
                          className="border-b border-[var(--desk-line)] last:border-0"
                        >
                          <td className="px-2 py-2.5 font-mono text-xs">
                            <button
                              type="button"
                              className="text-left text-[var(--desk-text)] underline-offset-2 hover:text-[var(--desk-accent)] hover:underline"
                              onClick={() =>
                                setDrawer({
                                  symbol: p.symbol,
                                  position: {
                                    symbol: p.symbol,
                                    qty: p.qty,
                                    cost: p.cost,
                                    last: p.last,
                                    pnl: p.pnl,
                                    pnlPct: p.pnlPct,
                                    weightPct: totalEquity > 0 ? (p.mv / totalEquity) * 100 : 0,
                                  },
                                })
                              }
                            >
                              {p.symbol}
                            </button>
                          </td>
                          <td className="px-2 py-2.5">{p.name}</td>
                          <td className="px-2 py-2.5">
                            <button
                              type="button"
                              className="text-sm text-[var(--desk-accent)] underline-offset-2 hover:underline"
                            >
                              {p.strategy}
                            </button>
                          </td>
                          <td className="px-2 py-2.5 font-mono">{fmtNum(p.qty, 0)}</td>
                          <td className="px-2 py-2.5 font-mono">
                            {p.pending ? "—" : fmtNum(p.cost)}
                          </td>
                          <td className="px-2 py-2.5 font-mono">
                            {p.pending ? "—" : fmtNum(p.last)}
                          </td>
                          <td className="px-2 py-2.5 font-mono">
                            {p.pending ? "—" : fmtNum(p.mv, 0)}
                          </td>
                          <td className={`px-2 py-2.5 font-mono ${pnlClass(p.pnl)}`}>
                            {p.pending ? "—" : fmtSigned(p.pnl, 0)}
                          </td>
                          <td className={`px-2 py-2.5 font-mono ${pnlClass(p.pnlPct)}`}>
                            {p.pending ? "—" : `${fmtSigned(p.pnlPct, 2)}%`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
              <CardHeader className="flex flex-wrap items-start justify-between gap-3 p-5 pb-3">
                <div>
                  <CardTitle className="text-base">信号</CardTitle>
                  <p className="mt-1 text-xs text-[var(--desk-mist)]">
                    按时间倒序展示最近策略买卖信号（来自告警通道）
                  </p>
                </div>
                <Chip variant="soft" color="accent">
                  {signalAlerts.length} / 100
                </Chip>
              </CardHeader>
              <CardContent className="p-5 pt-0">
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left text-sm">
                    <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                      <tr>
                        {["时间", "代码", "名称", "方向", "策略", "原因"].map((h) => (
                          <th key={h} className="px-2 py-2 font-medium">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {signalAlerts.length === 0 && (
                        <tr>
                          <td colSpan={6} className="px-2 py-8 text-center text-[var(--desk-mist)]">
                            暂无信号
                          </td>
                        </tr>
                      )}
                      {signalAlerts.map((a, i) => {
                        const side = (a.title || a.body || "").toUpperCase().includes("SELL")
                          ? "SELL"
                          : (a.title || a.body || "").toUpperCase().includes("BUY")
                            ? "BUY"
                            : "INFO";
                        return (
                          <tr
                            key={a.id ?? i}
                            className="border-b border-[var(--desk-line)] last:border-0"
                          >
                            <td className="px-2 py-2 font-mono text-xs text-[var(--desk-mist)]">
                              {a.created_at ? formatTime(a.created_at) : "—"}
                            </td>
                            <td className="px-2 py-2 font-mono text-xs">—</td>
                            <td className="px-2 py-2">{a.title || "—"}</td>
                            <td className="px-2 py-2">
                              <SideTag side={side} />
                            </td>
                            <td className="px-2 py-2">
                              <Chip size="sm" variant="soft" color="accent">
                                {a.category || "signal"}
                              </Chip>
                            </td>
                            <td className="max-w-xs truncate px-2 py-2 text-xs text-[var(--desk-mist)]">
                              {a.body || "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* 右栏 */}
          <div className="space-y-4">
            <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
              <CardHeader className="p-5 pb-2">
                <CardTitle className="text-base">策略 Runner</CardTitle>
                <p className="mt-1 text-xs text-[var(--desk-mist)]">
                  用最新日 K 评估 on_bar；仅试用/主力阶段可开仓，持仓可卖（与回测口径一致）
                </p>
              </CardHeader>
              <CardContent className="space-y-3 p-5 pt-2">
                <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
                  策略
                  <select
                    className={`${selectClass} block w-full`}
                    value={runStrategyId}
                    onChange={(e) => setRunStrategyId(e.target.value)}
                  >
                    {(strategies.length ? strategies : [{ id: "ma_cross", name: "双均线" }]).map(
                      (s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.id})
                        </option>
                      )
                    )}
                  </select>
                </label>
                <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
                  标的
                  <Input
                    aria-label="Runner 标的"
                    value={runSymbol}
                    onChange={(e) => setRunSymbol(e.target.value)}
                    placeholder="600519.SH"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="primary" isDisabled={busy} onPress={runPaperOnce}>
                    跑一次
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    isDisabled={busy}
                    onPress={runPaperWatchlist}
                  >
                    跑自选
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
              <CardHeader className="flex flex-wrap items-center justify-between gap-2 p-5 pb-2">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">资金面板</CardTitle>
                  <Chip color={running ? "success" : "warning"} variant="soft" size="sm">
                    {running ? "RUNNING" : "STOPPED"}
                  </Chip>
                </div>
                <Button
                  size="sm"
                  variant={running ? "danger" : "primary"}
                  onPress={() => setRunning((v) => !v)}
                >
                  {running ? "停止" : "启动"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-4 p-5 pt-2">
                <div>
                  <div className="text-3xl font-semibold tracking-tight text-[var(--desk-text)]">
                    {fmtNum(totalEquity, 0)}
                  </div>
                  <p className={`mt-1 text-sm ${pnlClass(pnlVsInit)}`}>
                    {fmtSigned(pnlVsInit, 0)} ({fmtSigned(pnlVsInitPct, 2)}%) vs 初始{" "}
                    {fmtNum(initialCash, 0)}
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-3">
                    <p className="text-xs text-[var(--desk-mist)]">持仓市值</p>
                    <p className="mt-1 font-mono text-lg">{fmtNum(posMv, 0)}</p>
                    <p className="text-xs text-[var(--desk-mist)]">
                      {totalEquity > 0 ? ((posMv / totalEquity) * 100).toFixed(1) : "0.0"}% ·{" "}
                      {heldCount} 只
                    </p>
                  </div>
                  <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-3">
                    <p className="text-xs text-[var(--desk-mist)]">可用现金</p>
                    <p className="mt-1 font-mono text-lg">{fmtNum(cash, 0)}</p>
                    <p className="text-xs text-[var(--desk-mist)]">
                      {totalEquity > 0 ? ((cash / totalEquity) * 100).toFixed(1) : "0.0"}%
                    </p>
                  </div>
                </div>
                <p className="text-xs text-[var(--desk-mist)]">
                  监控 {positions.length || watch.length} 只 · {nowLabel}
                  {running ? "" : " · 已停止"}
                </p>
                <div className="flex flex-wrap gap-3 border-t border-[var(--desk-line)] pt-3 text-xs">
                  <button
                    type="button"
                    className="text-[var(--desk-mist)] hover:text-[var(--desk-accent)]"
                    onClick={resetPaper}
                    disabled={busy}
                  >
                    重置持仓
                  </button>
                  <button
                    type="button"
                    className="text-[var(--desk-mist)] hover:text-[var(--desk-accent)]"
                    onClick={resetPaper}
                    disabled={busy}
                  >
                    清空历史
                  </button>
                  <span className="ml-auto text-[var(--desk-mist)]">
                    更新 {summary?.updated_at ? formatTime(summary.updated_at) : "—"}
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
              <CardHeader className="flex items-center justify-between p-5 pb-2">
                <div>
                  <CardTitle className="text-base">成交流水</CardTitle>
                  <p className="text-xs text-[var(--desk-mist)]">最近成交记录</p>
                </div>
                <Chip variant="soft" size="sm">
                  {trades.length} 条
                </Chip>
              </CardHeader>
              <CardContent className="max-h-56 overflow-auto p-5 pt-0">
                <table className="w-full border-collapse text-left text-xs">
                  <thead className="sticky top-0 bg-[var(--desk-panel)] text-[var(--desk-mist)]">
                    <tr>
                      {["时间", "代码", "方向", "数量", "价格"].map((h) => (
                        <th key={h} className="px-1 py-2 font-medium">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {trades.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-[var(--desk-mist)]">
                          暂无成交
                        </td>
                      </tr>
                    )}
                    {trades.map((t) => (
                      <tr key={t.id} className="border-b border-[var(--desk-line)] last:border-0">
                        <td className="px-1 py-2 font-mono text-[var(--desk-mist)]">
                          {t.created_at ? formatTime(t.created_at) : "—"}
                        </td>
                        <td className="px-1 py-2 font-mono">{t.symbol}</td>
                        <td className="px-1 py-2">
                          <SideTag side={t.side.toUpperCase()} />
                        </td>
                        <td className="px-1 py-2 font-mono">{fmtNum(t.qty, 0)}</td>
                        <td className="px-1 py-2 font-mono">{fmtNum(t.price)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
              <CardHeader className="p-5 pb-2">
                <CardTitle className="text-base">风控 / 熔断 / 下单</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 p-5 pt-0 text-sm">
                <RuleRow
                  tone="warning"
                  mark="风"
                  text={`仓位 ${risk?.max_order_position_pct ?? 10}% · 单笔 ${fmtNum(risk?.max_order_notional ?? 50000, 0)} · 日累计 ${fmtNum(risk?.max_daily_notional ?? 200000, 0)}（模拟/实盘共用，见设置）；白名单 ${risk?.whitelist?.length ?? 0} 只`}
                />
                <RuleRow
                  tone="danger"
                  mark="熔"
                  text={`Kill Switch ${risk?.kill_switch ? "已开启" : "关闭"}；未 ARM 时拒绝实盘下单`}
                />
                <RuleRow
                  tone="success"
                  mark="单"
                  text="监控模式成交写入 paper_trades；实盘需 ARM 后走 live 通道"
                />
              </CardContent>
            </Card>

            <div className="space-y-2">
              <AccordionRow
                title="龙头战法候选"
                badge="0 只"
                open={openPanel === "lead"}
                onToggle={() => setOpenPanel(openPanel === "lead" ? null : "lead")}
              >
                <p className="text-xs text-[var(--desk-mist)]">暂无候选标的。</p>
              </AccordionRow>
              <AccordionRow
                title="事件流 / 告警"
                badge={`${alerts.length} 条`}
                open={openPanel === "events"}
                onToggle={() => setOpenPanel(openPanel === "events" ? null : "events")}
              >
                <ul className="max-h-32 space-y-1 overflow-auto text-xs text-[var(--desk-mist)]">
                  {alerts.slice(0, 20).map((a, i) => (
                    <li key={a.id ?? i}>
                      {a.title || a.body || "告警"}
                    </li>
                  ))}
                  {alerts.length === 0 && <li>暂无告警</li>}
                </ul>
              </AccordionRow>
              <AccordionRow
                title="应急干预"
                badge="平时不用"
                badgeTone="warning"
                open={openPanel === "emergency"}
                onToggle={() => setOpenPanel(openPanel === "emergency" ? null : "emergency")}
              >
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="danger"
                    onPress={async () => {
                      try {
                        await api("/api/broker/risk", {
                          method: "POST",
                          body: JSON.stringify({ kill_switch: true }),
                        });
                        setLog("Kill Switch 已开启");
                        await refresh();
                      } catch (e) {
                        setLog(String(e));
                      }
                    }}
                  >
                    Kill Switch
                  </Button>
                </div>
              </AccordionRow>
            </div>
          </div>
        </div>
      )}
      <StockDetailDrawer
        open={drawer !== null}
        symbol={drawer?.symbol ?? ""}
        position={drawer?.position}
        onClose={() => setDrawer(null)}
      />
    </div>
  );
}

function SideTag({ side }: { side: string }) {
  const s = side.toUpperCase();
  const buy = s === "BUY";
  const sell = s === "SELL";
  return (
    <span
      className={[
        "inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide",
        buy
          ? "bg-[color-mix(in_srgb,var(--success)_25%,transparent)] text-[var(--success)]"
          : sell
            ? "bg-[color-mix(in_srgb,var(--danger)_25%,transparent)] text-[var(--danger)]"
            : "bg-[var(--desk-line)] text-[var(--desk-mist)]",
      ].join(" ")}
    >
      {s}
    </span>
  );
}

function RuleRow({
  mark,
  text,
  tone,
}: {
  mark: string;
  text: string;
  tone: "warning" | "danger" | "success";
}) {
  const bg =
    tone === "warning"
      ? "bg-[var(--warning)] text-[var(--warning-foreground)]"
      : tone === "danger"
        ? "bg-[var(--danger)] text-[var(--danger-foreground)]"
        : "bg-[var(--success)] text-[var(--success-foreground)]";
  return (
    <div className="flex gap-3">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded text-xs font-bold ${bg}`}>
        {mark}
      </span>
      <p className="text-[var(--desk-mist)] leading-6">{text}</p>
    </div>
  );
}

function AccordionRow({
  title,
  badge,
  badgeTone,
  open,
  onToggle,
  children,
}: {
  title: string;
  badge: string;
  badgeTone?: "warning";
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm"
        onClick={onToggle}
      >
        <span className="font-medium text-[var(--desk-text)]">{title}</span>
        <Chip
          size="sm"
          variant="soft"
          color={badgeTone === "warning" ? "warning" : "default"}
        >
          {badge}
        </Chip>
      </button>
      {open && <div className="border-t border-[var(--desk-line)] px-4 py-3">{children}</div>}
    </div>
  );
}

/**
 * @param n 数值
 * @param digits 小数位
 */
function fmtNum(n: number, digits = 2): string {
  return n.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtSigned(n: number, digits = 2): string {
  const s = fmtNum(Math.abs(n), digits);
  return n > 0 ? `+${s}` : n < 0 ? `-${s}` : s;
}

function pnlClass(n: number): string {
  if (n > 0) return "text-[var(--success)]";
  if (n < 0) return "text-[var(--danger)]";
  return "text-[var(--desk-mist)]";
}

function formatTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
