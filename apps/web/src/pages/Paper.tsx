import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Chip,
} from "@heroui/react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, beijingNowClock, formatBeijingTime, formatBeijingTimeShort } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import { getStrategyProfile } from "../stock/strategyProfiles";
import { SymbolSearchField } from "../stock/SymbolSearchField";
import type { PositionContext } from "../stock/types";
import type { PageLogProps } from "./types";

type PaperPosition = {
  symbol: string;
  qty: number;
  cost: number;
  strategy_id?: string | null;
};
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

type LivePositionRow = {
  symbol: string;
  qty: number;
  can_use_qty?: number;
  cost?: number;
  market_value?: number;
  frozen_qty?: number;
  strategy_id?: string | null;
  row_type?: "holding" | "sold";
};

type LiveSnapshot = {
  source?: string;
  mode?: string;
  message?: string;
  asset?: {
    cash?: number | null;
    frozen_cash?: number | null;
    market_value?: number | null;
    total_asset?: number | null;
    account_id?: string;
  } | null;
  positions?: LivePositionRow[];
  sold?: LivePositionRow[];
};

const selectClass =
  "rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2 py-1.5 text-xs text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

const symbolInputClass =
  "w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2 py-1.5 text-xs text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

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
  const [seedOpen, setSeedOpen] = useState(false);
  const [seedSymbol, setSeedSymbol] = useState("");
  const [seedStrategyId, setSeedStrategyId] = useState("manual");
  const [seedQtyMode, setSeedQtyMode] = useState<"shares" | "pct">("shares");
  const [seedQty, setSeedQty] = useState("100");
  const [seedPct, setSeedPct] = useState("10");
  const [sellOpen, setSellOpen] = useState<{
    symbol: string;
    name: string;
    qty: number;
    last: number;
  } | null>(null);
  const [sellQty, setSellQty] = useState("");
  const [stratModal, setStratModal] = useState<{
    symbol: string;
    name: string;
    currentId: string;
    mode: "paper" | "live";
  } | null>(null);
  const [liveQuotes, setLiveQuotes] = useState<
    Record<string, { name?: string; last?: number }>
  >({});
  const [stratPreviewId, setStratPreviewId] = useState("manual");
  const [stratExample, setStratExample] = useState("");
  const [stratExampleLoading, setStratExampleLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [openPanel, setOpenPanel] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [strategies, setStrategies] = useState<StrategyOpt[]>([]);
  const [runStrategyId, setRunStrategyId] = useState("ma_cross");
  const [runSymbol, setRunSymbol] = useState("600519.SH");
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [tradingMode, setTradingMode] = useState<TradingModeState | null>(null);
  const [liveSnap, setLiveSnap] = useState<LiveSnapshot | null>(null);
  const [qmtPing, setQmtPing] = useState<{
    real_ready?: boolean;
    query_ready?: boolean;
    mode?: string;
    account_id?: string;
    force_mock?: boolean;
  } | null>(null);
  const [runnerStatus, setRunnerStatus] = useState<{
    enabled?: boolean;
    strategy_id?: string;
    interval_minutes?: number;
    in_session?: boolean;
    last_run?: { at?: string | null; status?: string; filled?: number; count?: number; message?: string };
    note?: string;
  } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [paper, wl, al, rk, ap, tm, rs, live, ping] = await Promise.all([
        api<PaperSummary>("/api/broker/paper"),
        api<WatchRow[]>("/api/market/watchlist").catch(() => [] as WatchRow[]),
        api<AlertRow[]>("/api/alerts").catch(() => [] as AlertRow[]),
        api<RiskState>("/api/broker/risk").catch(() => null),
        api<{ items: ApprovalItem[] }>("/api/broker/approvals").catch(() => ({ items: [] })),
        api<TradingModeState>("/api/broker/trading-mode").catch(() => null),
        api<NonNullable<typeof runnerStatus>>("/api/broker/paper/runner").catch(() => null),
        api<LiveSnapshot>("/api/broker/live/positions").catch(() => null),
        api<NonNullable<typeof qmtPing>>("/api/broker/qmt/ping").catch(() => null),
      ]);
      setSummary(paper);
      setWatch(wl);
      setAlerts(al);
      setRisk(rk);
      setApprovals(ap.items || []);
      setTradingMode(tm);
      setRunnerStatus(rs);
      setLiveSnap(live);
      setQmtPing(ping);
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

  useEffect(() => {
    if (!seedOpen && !stratModal && !sellOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (seedOpen) setSeedOpen(false);
        if (stratModal) setStratModal(null);
        if (sellOpen) setSellOpen(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [seedOpen, stratModal, sellOpen]);

  useEffect(() => {
    if (!stratModal) return;
    const id = stratPreviewId;
    if (!id || id === "manual") {
      setStratExample(getStrategyProfile("manual").exampleHint);
      setStratExampleLoading(false);
      return;
    }
    let cancelled = false;
    setStratExampleLoading(true);
    void api<{ text?: string }>(`/api/strategies/${encodeURIComponent(id)}/source`)
      .then((res) => {
        if (cancelled) return;
        const text = (res.text || "").trim();
        setStratExample(text || getStrategyProfile(id).exampleHint);
      })
      .catch(() => {
        if (!cancelled) setStratExample(getStrategyProfile(id).exampleHint);
      })
      .finally(() => {
        if (!cancelled) setStratExampleLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stratModal, stratPreviewId]);

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
      const sid = p.strategy_id || "manual";
      const stratName =
        sid === "manual"
          ? "手动建仓"
          : strategies.find((s) => s.id === sid)?.name || sid;
      return {
        ...p,
        name: q?.name || p.symbol,
        strategy: stratName,
        last,
        mv,
        pnl,
        pnlPct,
        pending: p.qty <= 0,
      };
    });
    return rows;
  }, [summary, quoteMap, strategies]);

  const heldCount = positions.filter((p) => p.qty > 0).length;
  const pendingCount = positions.filter((p) => p.qty <= 0).length;

  const stratPreviewProfile = useMemo(() => {
    const name = strategies.find((s) => s.id === stratPreviewId)?.name;
    return getStrategyProfile(stratPreviewId, name);
  }, [stratPreviewId, strategies]);

  const stratDirty =
    !!stratModal && (stratPreviewId || "manual") !== (stratModal.currentId || "manual");

  /** 实盘：持仓 / 待审批 / 已卖出（同一表格） */
  const liveTableRows = useMemo(() => {
    type Row = {
      key: string;
      type: "holding" | "approval" | "sold";
      symbol: string;
      name: string;
      strategyId: string;
      strategyName: string;
      qty: number;
      canUse: number | null;
      cost: number | null;
      last: number | null;
      pnl: number | null;
      pnlPct: number | null;
      clientOrderId?: string;
    };
    const rows: Row[] = [];
    const nameOf = (sym: string) => liveQuotes[sym]?.name || quoteMap.get(sym)?.name || sym;
    const lastOf = (sym: string, fallback?: number) => {
      const q = liveQuotes[sym]?.last ?? quoteMap.get(sym)?.last;
      if (q != null && Number(q) > 0) return Number(q);
      return fallback != null && fallback > 0 ? fallback : null;
    };
    const stratName = (sid: string) =>
      sid === "manual"
        ? "手动建仓"
        : strategies.find((s) => s.id === sid)?.name || sid;

    for (const p of liveSnap?.positions || []) {
      const cost = p.cost != null ? Number(p.cost) : null;
      const lastFromMv =
        p.qty > 0 && p.market_value != null ? Number(p.market_value) / p.qty : undefined;
      const last = lastOf(p.symbol, lastFromMv);
      const pnl =
        cost != null && last != null && p.qty > 0 ? (last - cost) * p.qty : null;
      const pnlPct = cost != null && cost > 0 && last != null ? ((last - cost) / cost) * 100 : null;
      const sid = p.strategy_id || "manual";
      rows.push({
        key: `h:${p.symbol}`,
        type: "holding",
        symbol: p.symbol,
        name: nameOf(p.symbol),
        strategyId: sid,
        strategyName: stratName(sid),
        qty: p.qty,
        canUse: p.can_use_qty ?? p.qty,
        cost,
        last,
        pnl,
        pnlPct,
      });
    }
    for (const a of approvals) {
      const last = a.price != null ? Number(a.price) : lastOf(a.symbol);
      rows.push({
        key: `a:${a.client_order_id}`,
        type: "approval",
        symbol: a.symbol,
        name: nameOf(a.symbol),
        strategyId: "manual",
        strategyName: "—",
        qty: a.qty,
        canUse: null,
        cost: a.price != null ? Number(a.price) : null,
        last,
        pnl: null,
        pnlPct: null,
        clientOrderId: a.client_order_id,
      });
    }
    for (const p of liveSnap?.sold || []) {
      const cost = p.cost != null ? Number(p.cost) : null;
      const last = lastOf(p.symbol);
      const sid = p.strategy_id || "manual";
      rows.push({
        key: `s:${p.symbol}`,
        type: "sold",
        symbol: p.symbol,
        name: nameOf(p.symbol),
        strategyId: sid,
        strategyName: stratName(sid),
        qty: p.qty,
        canUse: 0,
        cost,
        last,
        pnl: null,
        pnlPct: null,
      });
    }
    return rows;
  }, [liveSnap?.positions, liveSnap?.sold, approvals, liveQuotes, quoteMap, strategies]);

  useEffect(() => {
    const syms = new Set<string>();
    for (const p of liveSnap?.positions || []) syms.add(p.symbol);
    for (const p of liveSnap?.sold || []) syms.add(p.symbol);
    for (const a of approvals) syms.add(a.symbol);
    if (!syms.size) {
      setLiveQuotes({});
      return;
    }
    let cancelled = false;
    void api<Record<string, { name?: string; last?: number; symbol?: string }>>(
      `/api/market/intraday/quote?symbols=${encodeURIComponent([...syms].join(","))}`
    )
      .then((snaps) => {
        if (cancelled) return;
        const map: Record<string, { name?: string; last?: number }> = {};
        for (const [sym, snap] of Object.entries(snaps || {})) {
          if (!sym || !snap) continue;
          map[sym] = { name: snap.name, last: snap.last };
        }
        setLiveQuotes(map);
      })
      .catch(() => {
        if (!cancelled) setLiveQuotes({});
      });
    return () => {
      cancelled = true;
    };
  }, [liveSnap?.positions, liveSnap?.sold, approvals]);

  const initialCash = summary?.initial_cash ?? 1_000_000;
  const cash = summary?.cash ?? 0;
  const posMv = positions.reduce((s, p) => s + p.mv, 0);
  const totalEquity = cash + posMv;
  const pnlVsInit = totalEquity - initialCash;
  const pnlVsInitPct = initialCash > 0 ? (pnlVsInit / initialCash) * 100 : 0;

  const trades = summary?.trades || [];
  const signalAlerts = alerts.filter((a) => (a.category || "").includes("signal") || true).slice(0, 30);

  /**
   * 打开持仓执行策略说明 / 切换弹框。
   * @param symbol 标的
   * @param name 标的名称
   * @param strategyId 当前策略
   * @param mode paper=模拟 / live=实盘
   */
  const openStrategyModal = (
    symbol: string,
    name: string,
    strategyId: string,
    mode: "paper" | "live" = "paper"
  ) => {
    const sid = strategyId || "manual";
    setStratPreviewId(sid);
    setStratModal({ symbol, name, currentId: sid, mode });
  };

  /**
   * 确认将预览策略应用到持仓。
   */
  const confirmPositionStrategy = async () => {
    if (!stratModal) return;
    const { symbol, mode } = stratModal;
    const strategyId = stratPreviewId || "manual";
    const path =
      mode === "live"
        ? `/api/broker/live/positions/${encodeURIComponent(symbol)}/strategy`
        : `/api/broker/paper/positions/${encodeURIComponent(symbol)}/strategy`;
    setBusy(true);
    try {
      const r = await api<{ ok: boolean; strategy_id?: string }>(path, {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId }),
      });
      setStratModal(null);
      setLog(`已将 ${symbol} 执行策略改为 ${r.strategy_id || strategyId}`);
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 打开添加股票弹框并重置表单。
   */
  const openSeedModal = () => {
    setSeedSymbol("");
    setSeedStrategyId(runStrategyId || strategies[0]?.id || "manual");
    setSeedQtyMode("shares");
    setSeedQty("100");
    setSeedPct("10");
    setSeedOpen(true);
  };

  /**
   * 弹框确认：走 seed 接口（自选 + 纸买建仓，豁免单笔限额/生命周期）。
   */
  const confirmSeed = async () => {
    const symbol = seedSymbol.trim();
    if (!symbol) {
      setLog("请选择股票代码");
      return;
    }
    const payload: Record<string, unknown> = {
      symbol,
      strategy_id: seedStrategyId || "manual",
      add_watchlist: true,
    };
    if (seedQtyMode === "pct") {
      const pct = Number(seedPct);
      if (!Number.isFinite(pct) || pct <= 0) {
        setLog("请填写有效仓位比例（%）");
        return;
      }
      payload.capital_pct = pct;
    } else {
      const qty = Number(seedQty);
      if (!Number.isFinite(qty) || qty < 100) {
        setLog("股数至少 100（1 手）");
        return;
      }
      payload.qty = qty;
    }
    setBusy(true);
    try {
      const result = await api<{
        status: string;
        symbol?: string;
        qty?: number;
        price?: number;
        strategy_id?: string;
        message?: string;
      }>("/api/broker/paper/seed", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (result.status === "filled") {
        setSeedOpen(false);
        setLog(
          `已建仓 ${result.symbol || symbol} × ${result.qty ?? "—"} @ ${
            result.price != null ? Number(result.price).toFixed(2) : "—"
          }（${result.strategy_id || seedStrategyId}）`
        );
      } else {
        setLog(`建仓失败: ${result.message || result.status}`);
      }
      await refresh();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 打开卖出弹框（默认全平）。
   * @param row 持仓行
   */
  const openSellModal = (row: {
    symbol: string;
    name: string;
    qty: number;
    last: number;
    pending?: boolean;
  }) => {
    if (row.pending || row.qty <= 0) {
      setLog("无可卖持仓");
      return;
    }
    setSellOpen({
      symbol: row.symbol,
      name: row.name,
      qty: row.qty,
      last: row.last,
    });
    setSellQty(String(row.qty));
  };

  /**
   * 确认卖出：调用 /api/broker/paper/sell。
   */
  const confirmSell = async () => {
    if (!sellOpen) return;
    const qty = Number(sellQty);
    if (!Number.isFinite(qty) || qty <= 0) {
      setLog("请填写有效卖出数量");
      return;
    }
    if (qty > sellOpen.qty) {
      setLog(`卖出数量不能超过持仓 ${sellOpen.qty}`);
      return;
    }
    setBusy(true);
    try {
      const result = await api<{
        status: string;
        symbol?: string;
        qty?: number;
        price?: number;
        message?: string;
      }>("/api/broker/paper/sell", {
        method: "POST",
        body: JSON.stringify({
          symbol: sellOpen.symbol,
          qty,
          price: sellOpen.last > 0 ? sellOpen.last : undefined,
        }),
      });
      if (result.status === "filled") {
        setSellOpen(null);
        setLog(
          `已卖出 ${result.symbol || sellOpen.symbol} × ${result.qty ?? qty} @ ${
            result.price != null ? Number(result.price).toFixed(2) : "—"
          }`
        );
      } else {
        setLog(`卖出失败: ${result.message || result.status}`);
      }
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

  const nowLabel = beijingNowClock();

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
            ? "纸交易：策略 Runner 评估信号并下模拟单"
            : "实盘：QMT 柜台持仓 · 待审批同表处理"}
        </p>
      </div>

      {tab === "live" ? (
        <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
          <div className="flex flex-col gap-4 p-5 pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <CardTitle className="text-base text-[var(--desk-text)]">实盘持仓</CardTitle>
                {qmtPing?.account_id ? (
                  <span className="font-mono text-xs text-[var(--desk-mist)]">
                    {qmtPing.account_id}
                  </span>
                ) : null}
                <Chip size="sm" variant="soft">
                  {liveSnap?.source === "qmt" ? "柜台" : "本地"}
                </Chip>
                <Chip
                  size="sm"
                  variant="soft"
                  color={qmtPing?.query_ready ? undefined : "warning"}
                >
                  {qmtPing?.query_ready ? "可查询" : "查询未就绪"}
                </Chip>
                <Chip
                  size="sm"
                  variant="soft"
                  color={qmtPing?.real_ready ? undefined : "warning"}
                >
                  {qmtPing?.real_ready ? "可真单" : "Mock 下单"}
                </Chip>
                {risk?.armed ? (
                  <Chip size="sm" variant="soft">
                    ARM
                  </Chip>
                ) : null}
                {risk?.kill_switch ? (
                  <Chip size="sm" variant="soft" color="danger">
                    Kill
                  </Chip>
                ) : null}
              </div>
              <Button
                className="shrink-0"
                size="sm"
                variant="secondary"
                onPress={() => void refresh()}
              >
                刷新
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[var(--desk-line)] bg-[var(--desk-line)] sm:grid-cols-4">
              <LiveStat
                label="可用资金"
                value={
                  liveSnap?.asset?.cash != null
                    ? fmtNum(Number(liveSnap.asset.cash), 0)
                    : "—"
                }
              />
              <LiveStat
                label="持仓市值"
                value={
                  liveSnap?.asset?.market_value != null
                    ? fmtNum(Number(liveSnap.asset.market_value), 0)
                    : "—"
                }
              />
              <LiveStat
                label="总资产"
                value={
                  liveSnap?.asset?.total_asset != null
                    ? fmtNum(Number(liveSnap.asset.total_asset), 0)
                    : "—"
                }
              />
              <LiveStat
                label="表内"
                value={`${(liveSnap?.positions || []).length}持仓 · ${approvals.length}审批 · ${(liveSnap?.sold || []).length}卖出`}
                mono={false}
              />
            </div>

            {liveSnap?.message ? (
              <p className="text-xs text-[var(--desk-accent)]">{liveSnap.message}</p>
            ) : null}
          </div>

          <div className="overflow-x-auto border-t border-[var(--desk-line)] px-2 pb-2 sm:px-3">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  {[
                    "代码",
                    "名称",
                    "策略",
                    "持仓",
                    "可用持仓",
                    "成本",
                    "现价",
                    "盈亏",
                    "盈亏率",
                    "类型",
                    "操作",
                  ].map((h) => (
                    <th key={h} className="px-2 py-2.5 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {liveTableRows.map((row) => {
                  const typeLabel =
                    row.type === "holding"
                      ? "持仓"
                      : row.type === "approval"
                        ? "待审批"
                        : "已卖出";
                  return (
                    <tr
                      key={row.key}
                      className="border-b border-[var(--desk-line)] last:border-0"
                    >
                      <td className="px-2 py-2 font-mono text-xs">
                        <button
                          type="button"
                          className="text-left text-[var(--desk-text)] underline-offset-2 hover:text-[var(--desk-accent)] hover:underline"
                          onClick={() =>
                            setDrawer({
                              symbol: row.symbol,
                              position: {
                                symbol: row.symbol,
                                qty: row.qty,
                                cost: row.cost ?? 0,
                                last: row.last ?? row.cost ?? 0,
                                pnl: row.pnl ?? 0,
                                pnlPct: row.pnlPct ?? 0,
                                weightPct: 0,
                              },
                            })
                          }
                        >
                          {row.symbol}
                        </button>
                      </td>
                      <td className="px-2 py-2">{row.name}</td>
                      <td className="px-2 py-2">
                        {row.type === "approval" ? (
                          <span className="text-[var(--desk-mist)]">—</span>
                        ) : (
                          <button
                            type="button"
                            className="max-w-[7.5rem] truncate text-left text-sm text-[var(--desk-accent)] underline-offset-2 hover:underline"
                            onClick={() =>
                              openStrategyModal(
                                row.symbol,
                                row.name,
                                row.strategyId,
                                "live"
                              )
                            }
                          >
                            {row.strategyName}
                          </button>
                        )}
                      </td>
                      <td className="px-2 py-2 font-mono">{fmtNum(row.qty, 0)}</td>
                      <td className="px-2 py-2 font-mono">
                        {row.canUse != null ? fmtNum(row.canUse, 0) : "—"}
                      </td>
                      <td className="px-2 py-2 font-mono">
                        {row.cost != null ? fmtNum(row.cost) : "—"}
                      </td>
                      <td className="px-2 py-2 font-mono">
                        {row.last != null ? fmtNum(row.last) : "—"}
                      </td>
                      <td
                        className={`px-2 py-2 font-mono ${
                          row.pnl != null ? pnlClass(row.pnl) : "text-[var(--desk-mist)]"
                        }`}
                      >
                        {row.pnl != null ? fmtSigned(row.pnl, 0) : "—"}
                      </td>
                      <td
                        className={`px-2 py-2 font-mono ${
                          row.pnlPct != null ? pnlClass(row.pnlPct) : "text-[var(--desk-mist)]"
                        }`}
                      >
                        {row.pnlPct != null ? `${fmtSigned(row.pnlPct, 2)}%` : "—"}
                      </td>
                      <td className="px-2 py-2">
                        <Chip
                          size="sm"
                          variant="soft"
                          color={
                            row.type === "approval"
                              ? "warning"
                              : row.type === "sold"
                                ? "danger"
                                : undefined
                          }
                        >
                          {typeLabel}
                        </Chip>
                      </td>
                      <td className="px-2 py-2">
                        {row.type === "approval" && row.clientOrderId ? (
                          <Button
                            size="sm"
                            variant="primary"
                            isDisabled={busy}
                            onPress={() => void approveOrder(row.clientOrderId!)}
                          >
                            通过
                          </Button>
                        ) : (
                          <span className="text-[var(--desk-mist)]">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {!liveTableRows.length && (
                  <tr>
                    <td colSpan={11} className="px-2 py-10 text-center text-[var(--desk-mist)]">
                      暂无数据
                      {qmtPing && !qmtPing.query_ready
                        ? "（请配置 QMT 路径与资金账号）"
                        : ""}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,1fr)]">
          {/* 左栏 */}
          <div className="space-y-4">
            <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
              <CardHeader className="flex flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
                <div className="min-w-0">
                  <CardTitle className="text-base text-[var(--desk-text)]">实时持仓</CardTitle>
                  <p className="mt-1 truncate text-xs text-[var(--desk-mist)]">
                    {heldCount} 只持仓 · {pendingCount} 只待入场 · 可更换执行策略
                  </p>
                </div>
                <Button
                  className="shrink-0"
                  size="sm"
                  variant="primary"
                  isDisabled={busy}
                  onPress={openSeedModal}
                >
                  + 添加股票
                </Button>
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
                          "操作",
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
                          <td colSpan={10} className="px-2 py-8 text-center text-[var(--desk-mist)]">
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
                              className="max-w-[9.5rem] truncate text-left text-sm text-[var(--desk-accent)] underline-offset-2 hover:underline"
                              aria-label={`${p.symbol} 执行策略`}
                              onClick={() =>
                                openStrategyModal(
                                  p.symbol,
                                  p.name,
                                  p.strategy_id || "manual"
                                )
                              }
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
                          <td className="px-2 py-2.5">
                            {!p.pending && p.qty > 0 ? (
                              <button
                                type="button"
                                className="text-xs text-[var(--danger)] underline-offset-2 hover:underline disabled:opacity-50"
                                disabled={busy}
                                onClick={() => openSellModal(p)}
                              >
                                卖出
                              </button>
                            ) : (
                              <span className="text-xs text-[var(--desk-mist)]">—</span>
                            )}
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
                              {formatBeijingTimeShort(a.created_at)}
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
                  <SymbolSearchField
                    value={runSymbol}
                    onChange={setRunSymbol}
                    className={symbolInputClass}
                    placeholder="代码 / 名称 / 拼音"
                    aria-label="搜索 Runner 标的"
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
                <div className="border-t border-[var(--desk-line)] pt-3 text-xs text-[var(--desk-mist)]">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span>
                      定时：{runnerStatus?.enabled ? "开" : "关"} · 间隔{" "}
                      {runnerStatus?.interval_minutes ?? "—"}m ·{" "}
                      {runnerStatus?.in_session ? "盘中" : "非盘中"}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      isDisabled={busy}
                      onPress={() =>
                        void (async () => {
                          setBusy(true);
                          try {
                            const next = !(runnerStatus?.enabled);
                            const r = await api<NonNullable<typeof runnerStatus>>(
                              "/api/broker/paper/runner",
                              {
                                method: "POST",
                                body: JSON.stringify({
                                  enabled: next,
                                  strategy_id: runStrategyId,
                                }),
                              }
                            );
                            setRunnerStatus(r);
                            setLog(
                              `Runner 定时已${next ? "开启" : "关闭"}` +
                                (r.note ? `（${r.note}）` : "")
                            );
                          } catch (e) {
                            setLog(String(e));
                          } finally {
                            setBusy(false);
                          }
                        })()
                      }
                    >
                      {runnerStatus?.enabled ? "关闭定时" : "开启定时"}
                    </Button>
                  </div>
                  <p>
                    上次：{formatBeijingTime(runnerStatus?.last_run?.at)} ·{" "}
                    {runnerStatus?.last_run?.status || "idle"} · 扫描{" "}
                    {runnerStatus?.last_run?.count ?? 0} · 成交{" "}
                    {runnerStatus?.last_run?.filled ?? 0}
                  </p>
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
                    更新 {formatBeijingTimeShort(summary?.updated_at)}
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
                          {formatBeijingTimeShort(t.created_at)}
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
                  text={`Kill Switch ${risk?.kill_switch ? "已开启" : "关闭"}；未 ARM 时拒绝实盘下单（见设置）`}
                />
                <RuleRow
                  tone="success"
                  mark="单"
                  text="纸成交写入 paper_trades；ARM/白名单/限额均在「设置 → 风控与实盘闸门」"
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
      {stratModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 cursor-default bg-black/50"
            aria-label="关闭策略说明"
            onClick={() => setStratModal(null)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="执行策略说明"
            className="relative z-10 flex max-h-[85vh] w-full max-w-lg flex-col rounded-xl border border-[var(--desk-line)] bg-[var(--desk-panel)] shadow-2xl"
          >
            <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--desk-line)] px-5 py-4">
              <div className="min-w-0">
                <h2 className="text-base font-medium text-[var(--desk-text)]">执行策略</h2>
                <p className="mt-1 truncate text-xs text-[var(--desk-mist)]">
                  {stratModal.symbol}
                  {stratModal.name ? ` · ${stratModal.name}` : ""} · 当前{" "}
                  {getStrategyProfile(
                    stratModal.currentId,
                    strategies.find((s) => s.id === stratModal.currentId)?.name
                  ).name}
                </p>
              </div>
              <Button size="sm" variant="ghost" onPress={() => setStratModal(null)}>
                关闭
              </Button>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
                切换策略（预览说明）
                <select
                  className={`${selectClass} block w-full`}
                  value={stratPreviewId}
                  onChange={(e) => setStratPreviewId(e.target.value)}
                >
                  <option value="manual">手动建仓</option>
                  {strategies.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.id})
                    </option>
                  ))}
                  {stratPreviewId &&
                  stratPreviewId !== "manual" &&
                  !strategies.some((s) => s.id === stratPreviewId) ? (
                    <option value={stratPreviewId}>{stratPreviewId}</option>
                  ) : null}
                </select>
              </label>
              <div>
                <div className="mb-1 text-xs font-medium text-[var(--desk-text)]">
                  {stratPreviewProfile.name}
                </div>
                <p className="text-sm text-[var(--desk-mist)]">{stratPreviewProfile.summary}</p>
              </div>
              <section className="space-y-1">
                <h3 className="text-xs font-medium text-[var(--desk-text)]">适用场景</h3>
                <p className="text-sm leading-relaxed text-[var(--desk-mist)]">
                  {stratPreviewProfile.scenario}
                </p>
              </section>
              <section className="space-y-1">
                <h3 className="text-xs font-medium text-[var(--desk-text)]">规则说明</h3>
                <p className="text-sm leading-relaxed text-[var(--desk-mist)]">
                  {stratPreviewProfile.rules}
                </p>
              </section>
              <section className="space-y-1">
                <h3 className="text-xs font-medium text-[var(--desk-text)]">示例</h3>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-3 font-mono text-[11px] leading-5 text-[var(--desk-text)]">
                  {stratExampleLoading ? "加载源码…" : stratExample}
                </pre>
              </section>
            </div>
            <div className="flex shrink-0 justify-end gap-2 border-t border-[var(--desk-line)] px-5 py-4">
              <Button size="sm" variant="secondary" onPress={() => setStratModal(null)}>
                取消
              </Button>
              <Button
                size="sm"
                variant="primary"
                isDisabled={busy || !stratDirty}
                onPress={() => void confirmPositionStrategy()}
              >
                {busy ? "应用中…" : stratDirty ? "应用此策略" : "已是当前策略"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {seedOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 cursor-default bg-black/50"
            aria-label="关闭添加股票"
            onClick={() => setSeedOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="添加股票建仓"
            className="relative z-10 w-full max-w-md rounded-xl border border-[var(--desk-line)] bg-[var(--desk-panel)] p-5 shadow-2xl"
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-medium text-[var(--desk-text)]">添加股票</h2>
                <p className="mt-1 text-xs text-[var(--desk-mist)]">
                  按市价买入建仓；不受单笔限额与策略阶段限制，仍受现金与最多持仓数约束
                </p>
              </div>
              <Button size="sm" variant="ghost" onPress={() => setSeedOpen(false)}>
                关闭
              </Button>
            </div>
            <div className="space-y-3">
              <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
                策略
                <select
                  className={`${selectClass} block w-full`}
                  value={seedStrategyId}
                  onChange={(e) => setSeedStrategyId(e.target.value)}
                >
                  <option value="manual">手动建仓</option>
                  {strategies.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.id})
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
                股票代码
                <SymbolSearchField
                  value={seedSymbol}
                  onChange={setSeedSymbol}
                  className={symbolInputClass}
                  placeholder="代码 / 名称 / 拼音"
                  aria-label="搜索建仓标的"
                />
              </label>
              <div className="space-y-1 text-xs text-[var(--desk-mist)]">
                <div>仓位 / 股数</div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={[
                      "rounded-lg border px-3 py-1.5 text-xs",
                      seedQtyMode === "shares"
                        ? "border-[var(--desk-accent)] bg-[var(--desk-ink)] text-[var(--desk-text)]"
                        : "border-[var(--desk-line)] text-[var(--desk-mist)]",
                    ].join(" ")}
                    onClick={() => setSeedQtyMode("shares")}
                  >
                    按股数
                  </button>
                  <button
                    type="button"
                    className={[
                      "rounded-lg border px-3 py-1.5 text-xs",
                      seedQtyMode === "pct"
                        ? "border-[var(--desk-accent)] bg-[var(--desk-ink)] text-[var(--desk-text)]"
                        : "border-[var(--desk-line)] text-[var(--desk-mist)]",
                    ].join(" ")}
                    onClick={() => setSeedQtyMode("pct")}
                  >
                    按仓位%
                  </button>
                </div>
                {seedQtyMode === "shares" ? (
                  <input
                    type="number"
                    min={100}
                    step={100}
                    value={seedQty}
                    onChange={(e) => setSeedQty(e.target.value)}
                    className={`${symbolInputClass} mt-1`}
                    aria-label="买入股数"
                    placeholder="100"
                  />
                ) : (
                  <input
                    type="number"
                    min={1}
                    max={100}
                    step={1}
                    value={seedPct}
                    onChange={(e) => setSeedPct(e.target.value)}
                    className={`${symbolInputClass} mt-1`}
                    aria-label="仓位百分比"
                    placeholder="占可用现金 %"
                  />
                )}
                <p className="text-[10px] opacity-80">
                  {seedQtyMode === "shares"
                    ? "须为 100 的整数倍；现金不足时自动下调手数"
                    : "按可用现金比例估算股数并向下取整到手数"}
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button size="sm" variant="secondary" onPress={() => setSeedOpen(false)}>
                取消
              </Button>
              <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void confirmSeed()}>
                {busy ? "提交中…" : "确认建仓"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {sellOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 cursor-default bg-black/50"
            aria-label="关闭卖出"
            onClick={() => setSellOpen(null)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="卖出持仓"
            className="relative z-10 w-full max-w-md rounded-xl border border-[var(--desk-line)] bg-[var(--desk-panel)] p-5 shadow-2xl"
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-medium text-[var(--desk-text)]">卖出持仓</h2>
                <p className="mt-1 text-xs text-[var(--desk-mist)]">
                  {sellOpen.name} · {sellOpen.symbol} · 持仓 {fmtNum(sellOpen.qty, 0)} 股 · 参考价{" "}
                  {fmtNum(sellOpen.last)}
                </p>
              </div>
              <Button size="sm" variant="ghost" onPress={() => setSellOpen(null)}>
                关闭
              </Button>
            </div>
            <div className="space-y-3">
              <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
                卖出数量
                <input
                  type="number"
                  min={1}
                  step={1}
                  max={sellOpen.qty}
                  value={sellQty}
                  onChange={(e) => setSellQty(e.target.value)}
                  className={symbolInputClass}
                  aria-label="卖出股数"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onPress={() => setSellQty(String(sellOpen.qty))}
                >
                  全部卖出
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onPress={() =>
                    setSellQty(String(Math.max(1, Math.floor(sellOpen.qty / 2))))
                  }
                >
                  卖一半
                </Button>
              </div>
              <p className="text-[10px] text-[var(--desk-mist)]">
                按当前参考价市价成交；卖出不受单笔限额与策略阶段限制
              </p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button size="sm" variant="secondary" onPress={() => setSellOpen(null)}>
                取消
              </Button>
              <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void confirmSell()}>
                {busy ? "提交中…" : "确认卖出"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

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
 * 实盘顶栏指标格。
 * @param props 标签与展示值
 */
function LiveStat({
  label,
  value,
  mono = true,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="bg-[var(--desk-panel)] px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-[var(--desk-mist)]">
        {label}
      </div>
      <div
        className={[
          "mt-1 truncate text-sm text-[var(--desk-text)]",
          mono ? "font-mono tabular-nums" : "text-xs leading-5",
        ].join(" ")}
      >
        {value}
      </div>
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

