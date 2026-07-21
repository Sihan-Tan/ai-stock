import { Button, Card, CardContent } from "@heroui/react";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { FactorCatalog } from "../factors/FactorCatalog";
import { FactorCharts } from "../factors/FactorCharts";
import type { FactorMeta, FactorSeriesResponse } from "../factors/types";
import { SymbolSearchField } from "../stock/SymbolSearchField";
import { DateRangePresetSelect } from "../ui/DateRangePresetSelect";
import {
  defaultDateRangeValue,
  type DateRangeValue,
  validateDateRange,
} from "../ui/dateRange";
import type { PageLogProps } from "./types";

/** 副图同时勾选上限（主图 overlay 不计入） */
const PANEL_LIMIT = 12;

/** 因子模块 Tab */
const FACTOR_TABS = [
  { id: "charts", label: "因子图表" },
  { id: "models", label: "模型训练" },
] as const;

type FactorTabId = (typeof FACTOR_TABS)[number]["id"];

/**
 * 从目录构建初始勾选：overlay 默认全选，panel 默认最多 PANEL_LIMIT 个（按目录顺序）。
 * @param rows 因子目录
 */
function buildInitialSelected(rows: FactorMeta[]): { selected: Set<string>; panelTruncated: boolean } {
  const selected = new Set<string>();
  let panelDefaultCount = 0;
  let panelDefaultTotal = 0;

  for (const factor of rows) {
    if (!factor.default_enabled) continue;
    if (factor.plot === "overlay") {
      selected.add(factor.name);
      continue;
    }
    if (factor.plot === "panel") {
      panelDefaultTotal += 1;
      if (panelDefaultCount < PANEL_LIMIT) {
        selected.add(factor.name);
        panelDefaultCount += 1;
      }
    }
  }

  return { selected, panelTruncated: panelDefaultTotal > PANEL_LIMIT };
}

/**
 * 统计当前已选副图（panel）数量。
 * @param selected 勾选集合
 * @param factors 目录
 */
function countSelectedPanels(selected: Set<string>, factors: FactorMeta[]): number {
  return [...selected].filter((n) => factors.find((f) => f.name === n)?.plot === "panel").length;
}

/**
 * 因子页：Tab 切换「因子图表」与「模型训练」。
 * @param props 页面日志写入方法
 */
export default function Factors({ setLog }: PageLogProps) {
  const [tab, setTab] = useState<FactorTabId>("charts");
  const [factors, setFactors] = useState<FactorMeta[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [symbol, setSymbol] = useState("600519.SH");
  const [dateRange, setDateRange] = useState<DateRangeValue>(() => defaultDateRangeValue());
  const [series, setSeries] = useState<FactorSeriesResponse | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<unknown[]>([]);
  const [comparison, setComparison] = useState<unknown>(null);
  const [trainSymbols, setTrainSymbols] = useState<string[]>(["600519.SH"]);
  const [trainRange, setTrainRange] = useState<DateRangeValue>(() => defaultDateRangeValue());
  const [trainBusy, setTrainBusy] = useState(false);
  const [trainAddSymbol, setTrainAddSymbol] = useState("");
  const catalogReady = useRef(false);
  /** 序列请求序号，用于丢弃过期响应 */
  const seriesRequestIdRef = useRef(0);

  const selectedMetas = useMemo(
    () => factors.filter((f) => selected.has(f.name)),
    [factors, selected]
  );

  const panelSelectedCount = useMemo(
    () => countSelectedPanels(selected, factors),
    [selected, factors]
  );

  /**
   * 拉取因子目录与 ML 模型列表。
   */
  const refreshMeta = useCallback(async () => {
    try {
      const [factorRes, modelRows] = await Promise.all([
        api<{ factors: FactorMeta[] }>("/api/factors"),
        api<unknown[]>("/api/ml/models"),
      ]);
      const rows = (factorRes.factors ?? []).filter((f) => f.enabled);
      setFactors(rows);
      setModels(modelRows);
      if (!catalogReady.current) {
        catalogReady.current = true;
        const { selected: initial, panelTruncated } = buildInitialSelected(rows);
        setSelected(initial);
        if (panelTruncated) {
          setLog(`默认副图超过 ${PANEL_LIMIT}，已截取前 ${PANEL_LIMIT} 个`);
        }
      }
    } catch (error) {
      setLog(String(error));
    }
  }, [setLog]);

  /**
   * 按当前勾选与区间拉取因子序列；仅最新请求可写回状态。
   */
  const loadSeries = useCallback(async () => {
    const requestId = ++seriesRequestIdRef.current;
    if (!symbol.trim() || selected.size === 0) {
      if (requestId === seriesRequestIdRef.current) {
        setSeries(null);
        setSeriesError(null);
        setLoading(false);
      }
      return;
    }
    const rangeError = validateDateRange(dateRange.start, dateRange.end);
    if (rangeError) {
      if (requestId === seriesRequestIdRef.current) {
        setSeries(null);
        setSeriesError(rangeError);
        setLoading(false);
      }
      return;
    }
    const { start, end } = dateRange;
    const names = [...selected].join(",");
    setLoading(true);
    setSeriesError(null);
    try {
      const data = await api<FactorSeriesResponse>(
        `/api/factors/series?symbol=${encodeURIComponent(symbol.trim())}&names=${encodeURIComponent(names)}&start=${start}&end=${end}`
      );
      if (requestId !== seriesRequestIdRef.current) return;
      setSeries(data);
    } catch (error) {
      if (requestId !== seriesRequestIdRef.current) return;
      setSeries(null);
      setSeriesError(String(error));
      setLog(String(error));
    } finally {
      if (requestId === seriesRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, [symbol, selected, dateRange, setLog]);

  useEffect(() => {
    void refreshMeta();
  }, [refreshMeta]);

  useEffect(() => {
    if (!catalogReady.current) return;
    if (tab !== "charts") return;
    const timer = window.setTimeout(() => {
      void loadSeries();
    }, 300);
    return () => window.clearTimeout(timer);
  }, [loadSeries, tab]);

  /**
   * 切换因子勾选；副图超过上限时拒绝并写日志。
   * @param name 因子 name
   */
  const onToggle = (name: string) => {
    if (selected.has(name)) {
      const next = new Set(selected);
      next.delete(name);
      setSelected(next);
      return;
    }
    const meta = factors.find((f) => f.name === name);
    if (meta?.plot === "panel" && countSelectedPanels(selected, factors) >= PANEL_LIMIT) {
      setLog(`副图最多同时勾选 ${PANEL_LIMIT} 个，请先取消部分副图因子（主图均线等不受限）`);
      return;
    }
    const next = new Set(selected);
    next.add(name);
    setSelected(next);
  };

  /**
   * 向训练池添加标的（去重）。
   * @param sym 标准代码
   */
  const addTrainSymbol = (sym: string) => {
    const code = sym.trim().toUpperCase();
    if (!code) return;
    setTrainSymbols((prev) => (prev.includes(code) ? prev : [...prev, code]));
    setTrainAddSymbol("");
  };

  /**
   * 从训练池移除标的。
   * @param sym 标准代码
   */
  const removeTrainSymbol = (sym: string) => {
    setTrainSymbols((prev) => prev.filter((s) => s !== sym));
  };

  /**
   * 导入自选股并入训练池。
   */
  const importWatchlist = async () => {
    try {
      const rows = await api<Array<{ symbol: string }>>("/api/market/watchlist");
      const next = new Set(trainSymbols);
      for (const row of rows) {
        if (row.symbol) next.add(row.symbol);
      }
      setTrainSymbols([...next]);
      setLog(`已导入自选，训练池共 ${next.size} 只`);
    } catch (error) {
      setLog(String(error));
    }
  };

  /**
   * 对当前股票池做 LGBM / XGB 对比训练。
   */
  const trainBoth = async () => {
    const rangeError = validateDateRange(trainRange.start, trainRange.end);
    if (rangeError) {
      setLog(rangeError);
      return;
    }
    if (trainSymbols.length === 0) {
      setLog("请先添加至少一只训练股票");
      return;
    }
    setTrainBusy(true);
    try {
      const result = await api("/api/ml/train-symbols", {
        method: "POST",
        body: JSON.stringify({
          symbols: trainSymbols,
          start: trainRange.start,
          end: trainRange.end,
        }),
      });
      setComparison(result);
      await refreshMeta();
      setLog(`双引擎对比训练完成（${trainSymbols.length} 只）`);
    } catch (error) {
      setLog(String(error));
    } finally {
      setTrainBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="space-y-4 p-5">
          <div
            role="tablist"
            aria-label="因子模块"
            className="flex gap-1 overflow-x-auto border-b border-[var(--desk-line)] pb-px"
          >
            {FACTOR_TABS.map((item) => {
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  id={`factors-tab-${item.id}`}
                  aria-controls={`factors-panel-${item.id}`}
                  className={[
                    "shrink-0 rounded-t-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "border-b-2 border-[var(--desk-accent)] font-medium text-[var(--desk-text)]"
                      : "border-b-2 border-transparent text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
                  ].join(" ")}
                  onClick={() => setTab(item.id)}
                >
                  {item.label}
                  {item.id === "charts" && selected.size > 0 ? (
                    <span className="ml-1.5 font-mono text-xs opacity-70">{selected.size}</span>
                  ) : null}
                </button>
              );
            })}
          </div>

          <div
            role="tabpanel"
            id={`factors-panel-${tab}`}
            aria-labelledby={`factors-tab-${tab}`}
            className="min-h-[280px]"
          >
            {tab === "charts" && (
              <TabPanel title="TA-Lib 因子目录与主副图">
                <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
                  <FactorCatalog
                    factors={factors}
                    selected={selected}
                    onToggle={onToggle}
                    query={query}
                    onQuery={setQuery}
                    panelLimit={PANEL_LIMIT}
                    panelSelectedCount={panelSelectedCount}
                  />
                  <div className="space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/30 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="w-[240px] max-w-full shrink-0">
                        <SymbolSearchField
                          value={symbol}
                          onChange={setSymbol}
                          className="w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]"
                        />
                      </div>
                      {series?.engine && (
                        <span className="text-xs text-[var(--desk-mist)]">engine: {series.engine}</span>
                      )}
                      <div className="ml-auto flex flex-wrap items-center gap-2">
                        <DateRangePresetSelect value={dateRange} onChange={setDateRange} />
                        <Button size="sm" variant="primary" onPress={() => void loadSeries()} isDisabled={loading}>
                          {loading ? "计算中…" : "计算"}
                        </Button>
                      </div>
                    </div>
                    {seriesError && <p className="text-sm text-red-400">{seriesError}</p>}
                    <FactorCharts data={series} metas={selectedMetas} />
                  </div>
                </div>
              </TabPanel>
            )}

            {tab === "models" && (
              <TabPanel
                title="模型训练"
                actions={
                  <div className="flex shrink-0 gap-2">
                    <Button size="sm" variant="secondary" onPress={() => void refreshMeta()}>
                      刷新列表
                    </Button>
                    <Button
                      size="sm"
                      variant="primary"
                      isDisabled={trainBusy || trainSymbols.length === 0}
                      onPress={() => void trainBoth()}
                    >
                      {trainBusy ? "训练中…" : "开始对比训练"}
                    </Button>
                  </div>
                }
              >
                <div className="space-y-4">
                  <section className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/25 px-4 py-3">
                    <h4 className="text-sm font-medium text-[var(--desk-text)]">做什么、为什么</h4>
                    <p className="mt-2 text-sm leading-relaxed text-[var(--desk-mist)]">
                      用你选定股票的<strong className="font-medium text-[var(--desk-text)]">本地日线</strong>
                      算出动量 / RSI / MACD 等特征，标签为「次日是否上涨」，分别训练
                      LightGBM 与 XGBoost，对比样本数、上涨占比与训练集准确率。
                      目的是做<strong className="font-medium text-[var(--desk-text)]">研究侧引擎对比</strong>
                      ，帮助判断哪套树模型更适合当前股票池与区间——不是实盘信号，也不替代回测与风控。
                    </p>
                    <ul className="mt-3 grid gap-1.5 text-xs text-[var(--desk-mist)] sm:grid-cols-3">
                      <li className="rounded-md border border-[var(--desk-line)]/80 px-2.5 py-2">
                        数据：本地日线（缺数据会跳过）
                      </li>
                      <li className="rounded-md border border-[var(--desk-line)]/80 px-2.5 py-2">
                        标签：次日收盘相对今日是否上涨
                      </li>
                      <li className="rounded-md border border-[var(--desk-line)]/80 px-2.5 py-2">
                        产出：登记模型 + 对比指标
                      </li>
                    </ul>
                  </section>

                  <section className="space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/30 p-4">
                    <div className="flex flex-wrap items-end justify-between gap-2">
                      <div>
                        <h4 className="text-sm font-medium text-[var(--desk-text)]">训练股票池</h4>
                        <p className="mt-0.5 text-xs text-[var(--desk-mist)]">
                          搜索添加或导入自选；点击代码可移除（当前 {trainSymbols.length} 只）
                        </p>
                      </div>
                      <DateRangePresetSelect value={trainRange} onChange={setTrainRange} />
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="w-[240px] max-w-full shrink-0">
                        <SymbolSearchField
                          value={trainAddSymbol}
                          onChange={addTrainSymbol}
                          placeholder="添加训练标的"
                          aria-label="添加训练标的"
                          className="w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]"
                        />
                      </div>
                      <Button size="sm" variant="secondary" onPress={() => void importWatchlist()}>
                        导入自选
                      </Button>
                    </div>
                    <div className="flex min-h-[40px] flex-wrap gap-2">
                      {trainSymbols.length === 0 ? (
                        <span className="text-sm text-[var(--desk-mist)]">
                          暂无标的。请搜索添加，或点「导入自选」。
                        </span>
                      ) : (
                        trainSymbols.map((sym) => (
                          <button
                            key={sym}
                            type="button"
                            className="rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 py-1 font-mono text-xs text-[var(--desk-text)] transition-colors hover:border-[var(--desk-mist)] hover:text-[var(--danger)]"
                            onClick={() => removeTrainSymbol(sym)}
                            aria-label={`移除 ${sym}`}
                          >
                            {sym}
                            <span className="ml-1.5 opacity-60">×</span>
                          </button>
                        ))
                      )}
                    </div>
                  </section>

                  {comparison !== null && (
                    <TrainComparisonPanel comparison={comparison} />
                  )}

                  <RegisteredModelsPanel models={models} onChanged={refreshMeta} setLog={setLog} />
                </div>
              </TabPanel>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Tab 内容区标题与正文；可选右侧操作区。
 * @param props 标题、操作按钮与子节点
 */
function TabPanel({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="space-y-3 pt-1">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-[var(--desk-text)]">{title}</h3>
        {actions}
      </div>
      {children}
    </div>
  );
}

type TrainEngineResult = {
  engine?: string;
  model_id?: string;
  metrics?: {
    n_samples?: number;
    n_symbols?: number;
    train_pos_rate?: number;
    train_accuracy?: number;
  };
  symbols_used?: string[];
  skipped?: Array<{ symbol?: string; reason?: string }>;
  features?: string[];
};

type TrainComparison = {
  lightgbm?: TrainEngineResult;
  xgboost?: TrainEngineResult;
  start?: string;
  end?: string;
};

type RegisteredModel = {
  model_id?: string;
  engine?: string;
  metrics?: Record<string, number | string>;
  features?: string[];
  path?: string;
  /** 是否已出现在因子目录 */
  as_factor?: boolean;
};

/**
 * 格式化百分比（0–1 → 百分数）。
 * @param value 比例
 */
function formatPct(value: number | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * 单引擎训练结果卡片。
 * @param props 引擎名与结果
 */
function EngineResultCard({
  title,
  result,
}: {
  title: string;
  result: TrainEngineResult | undefined;
}) {
  if (!result) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--desk-line)] px-3 py-4 text-sm text-[var(--desk-mist)]">
        {title}：暂无结果
      </div>
    );
  }
  const m = result.metrics ?? {};
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/40 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h5 className="text-sm font-medium text-[var(--desk-text)]">{title}</h5>
        <span className="font-mono text-xs text-[var(--desk-mist)]">{result.model_id ?? "—"}</span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-xs text-[var(--desk-mist)]">样本数</dt>
          <dd className="font-mono text-[var(--desk-text)]">{m.n_samples ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--desk-mist)]">用到标的</dt>
          <dd className="font-mono text-[var(--desk-text)]">{m.n_symbols ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--desk-mist)]">上涨占比</dt>
          <dd className="font-mono text-[var(--desk-text)]">{formatPct(m.train_pos_rate)}</dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--desk-mist)]">训练准确率</dt>
          <dd className="font-mono text-[var(--desk-text)]">{formatPct(m.train_accuracy)}</dd>
        </div>
      </dl>
      {result.skipped && result.skipped.length > 0 ? (
        <p className="mt-2 text-xs text-[var(--desk-mist)]">
          跳过 {result.skipped.length} 只（日线不足或清洗后样本过少）
        </p>
      ) : null}
    </div>
  );
}

/**
 * 最近一次对比训练结果。
 * @param props 对比响应
 */
function TrainComparisonPanel({ comparison }: { comparison: unknown }) {
  const data = comparison as TrainComparison;
  return (
    <section className="space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/20 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-medium text-[var(--desk-text)]">本次对比结果</h4>
        {(data.start || data.end) && (
          <span className="font-mono text-xs text-[var(--desk-mist)]">
            {data.start ?? "?"} → {data.end ?? "?"}
          </span>
        )}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <EngineResultCard title="LightGBM" result={data.lightgbm} />
        <EngineResultCard title="XGBoost" result={data.xgboost} />
      </div>
      <p className="text-xs text-[var(--desk-mist)]">
        训练集准确率仅作引擎对比参考，存在过拟合可能；上线前请结合回测与样本外验证。
      </p>
    </section>
  );
}

/**
 * 已登记模型列表：放入/移出因子目录、删除。
 * @param props 模型数组、变更回调与日志
 */
function RegisteredModelsPanel({
  models,
  onChanged,
  setLog,
}: {
  models: unknown[];
  onChanged: () => void | Promise<void>;
  setLog: (s: string) => void;
}) {
  const rows = (models as RegisteredModel[]) ?? [];
  const [busyId, setBusyId] = useState<string | null>(null);

  /**
   * 切换模型是否进入因子列表。
   * @param modelId 模型 id
   * @param asFactor 是否放入
   */
  async function setAsFactor(modelId: string, asFactor: boolean) {
    setBusyId(modelId);
    try {
      await api(`/api/ml/models/${encodeURIComponent(modelId)}/as-factor`, {
        method: "POST",
        body: JSON.stringify({ as_factor: asFactor }),
      });
      await onChanged();
      setLog(
        asFactor
          ? `已放入因子列表：${modelId}，可到「因子图表」勾选`
          : `已移出因子列表：${modelId}`,
      );
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusyId(null);
    }
  }

  /**
   * 确认后删除登记模型。
   * @param modelId 模型 id
   */
  async function deleteModel(modelId: string) {
    if (!window.confirm(`确认删除模型 ${modelId}？此操作不可恢复。`)) return;
    setBusyId(modelId);
    try {
      await api(`/api/ml/models/${encodeURIComponent(modelId)}`, { method: "DELETE" });
      await onChanged();
      setLog(`已删除模型：${modelId}`);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="space-y-2 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/20 p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-medium text-[var(--desk-text)]">已登记模型</h4>
        <span className="text-xs text-[var(--desk-mist)]">{rows.length} 个</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-[var(--desk-mist)]">尚无登记模型。完成一次对比训练后会出现在这里。</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
              <tr>
                <th className="px-2 py-2 font-medium">model_id</th>
                <th className="px-2 py-2 font-medium">引擎</th>
                <th className="px-2 py-2 font-medium">样本</th>
                <th className="px-2 py-2 font-medium">准确率</th>
                <th className="px-2 py-2 font-medium">特征数</th>
                <th className="px-2 py-2 font-medium">状态</th>
                <th className="px-2 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const metrics = row.metrics ?? {};
                const acc = typeof metrics.train_accuracy === "number" ? metrics.train_accuracy : undefined;
                const n = metrics.n_samples;
                const id = row.model_id ?? "";
                const busy = busyId === id;
                const inList = Boolean(row.as_factor);
                return (
                  <tr key={row.model_id} className="border-b border-[var(--desk-line)] last:border-0">
                    <td className="px-2 py-2 font-mono text-xs text-[var(--desk-text)]">
                      {row.model_id ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-[var(--desk-mist)]">{row.engine ?? "—"}</td>
                    <td className="px-2 py-2 font-mono text-[var(--desk-mist)]">
                      {typeof n === "number" ? n : "—"}
                    </td>
                    <td className="px-2 py-2 font-mono text-[var(--desk-mist)]">{formatPct(acc)}</td>
                    <td className="px-2 py-2 font-mono text-[var(--desk-mist)]">
                      {row.features?.length ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-[var(--desk-mist)]">
                      {inList ? "已在因子列表" : "未放入"}
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex flex-wrap items-center gap-2">
                        {inList ? (
                          <button
                            type="button"
                            className="text-xs text-[var(--desk-text)] underline-offset-2 hover:underline disabled:opacity-50"
                            disabled={!id || busy}
                            onClick={() => void setAsFactor(id, false)}
                          >
                            移出因子列表
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="text-xs text-[var(--desk-text)] underline-offset-2 hover:underline disabled:opacity-50"
                            disabled={!id || busy}
                            onClick={() => void setAsFactor(id, true)}
                          >
                            放入因子列表
                          </button>
                        )}
                        <button
                          type="button"
                          className="text-xs text-[var(--desk-mist)] underline-offset-2 hover:underline disabled:opacity-50"
                          disabled={!id || busy}
                          onClick={() => void deleteModel(id)}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
