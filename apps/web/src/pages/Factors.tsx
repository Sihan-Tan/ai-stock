import { Button, Card, CardContent } from "@heroui/react";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, beijingToday } from "../api";
import { FactorCatalog } from "../factors/FactorCatalog";
import { FactorCharts } from "../factors/FactorCharts";
import type { FactorMeta, FactorSeriesResponse } from "../factors/types";
import { SymbolSearchField } from "../stock/SymbolSearchField";
import type { PageLogProps } from "./types";

/** 副图同时勾选上限（主图 overlay 不计入） */
const PANEL_LIMIT = 12;

/** 因子模块 Tab */
const FACTOR_TABS = [
  { id: "charts", label: "因子图表" },
  { id: "models", label: "模型训练" },
] as const;

type FactorTabId = (typeof FACTOR_TABS)[number]["id"];

type RangeKey = "3m" | "1y";

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
 * 按区间推算 start/end（北京日期 YYYY-MM-DD）。
 * @param range 近3月 / 近1年
 */
function rangeBounds(range: RangeKey): { start: string; end: string } {
  const end = beijingToday();
  const endDate = new Date(`${end}T12:00:00Z`);
  const startDate = new Date(endDate);
  if (range === "3m") {
    startDate.setUTCMonth(startDate.getUTCMonth() - 3);
  } else {
    startDate.setUTCFullYear(startDate.getUTCFullYear() - 1);
  }
  const start = startDate.toISOString().slice(0, 10);
  return { start, end };
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
  const [range, setRange] = useState<RangeKey>("1y");
  const [series, setSeries] = useState<FactorSeriesResponse | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<unknown[]>([]);
  const [comparison, setComparison] = useState<unknown>(null);
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
    const { start, end } = rangeBounds(range);
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
  }, [symbol, selected, range, setLog]);

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

  const trainBoth = async () => {
    try {
      setComparison(await api("/api/ml/compare-engines", { method: "POST" }));
      await refreshMeta();
      setLog("双引擎对比训练完成");
    } catch (error) {
      setLog(String(error));
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
                      <div className="min-w-[200px] flex-1">
                        <SymbolSearchField
                          value={symbol}
                          onChange={setSymbol}
                          className="w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]"
                        />
                      </div>
                      <select
                        value={range}
                        onChange={(e) => setRange(e.target.value as RangeKey)}
                        aria-label="时间区间"
                        className="rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 py-1.5 text-sm text-[var(--desk-text)]"
                      >
                        <option value="3m">近3月</option>
                        <option value="1y">近1年</option>
                      </select>
                      <Button size="sm" variant="primary" onPress={() => void loadSeries()} isDisabled={loading}>
                        {loading ? "计算中…" : "计算"}
                      </Button>
                      {series?.engine && (
                        <span className="text-xs text-[var(--desk-mist)]">engine: {series.engine}</span>
                      )}
                    </div>
                    {seriesError && <p className="text-sm text-red-400">{seriesError}</p>}
                    <FactorCharts data={series} metas={selectedMetas} />
                  </div>
                </div>
              </TabPanel>
            )}

            {tab === "models" && (
              <TabPanel
                title="机器学习模型"
                actions={
                  <div className="flex shrink-0 gap-2">
                    <Button size="sm" variant="primary" onPress={() => void trainBoth()}>
                      LGBM vs XGB 对比训练
                    </Button>
                    <Button size="sm" variant="secondary" onPress={() => void refreshMeta()}>
                      刷新
                    </Button>
                  </div>
                }
              >
                <pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">
                  {JSON.stringify(models, null, 2)}
                </pre>
                {comparison !== null && (
                  <div className="mt-4 space-y-2">
                    <div className="text-sm font-medium text-[var(--desk-text)]">引擎对比</div>
                    <pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">
                      {JSON.stringify(comparison, null, 2)}
                    </pre>
                  </div>
                )}
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
