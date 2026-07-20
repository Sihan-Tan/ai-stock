import { Button, Card, CardContent, CardHeader, CardTitle } from "@heroui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, beijingToday } from "../api";
import { FactorCatalog } from "../factors/FactorCatalog";
import { FactorCharts } from "../factors/FactorCharts";
import type { FactorMeta, FactorSeriesResponse } from "../factors/types";
import { SymbolSearchField } from "../stock/SymbolSearchField";
import type { PageLogProps } from "./types";

const PANEL_LIMIT = 6;

type RangeKey = "3m" | "1y";

/**
 * 从目录构建初始勾选：overlay 默认全选，panel 默认最多 6 个（按目录顺序）。
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
 * 因子页：左目录勾选，右主/副图；下方保留 ML 模型与双引擎对比。
 * @param props 页面日志写入方法
 */
export default function Factors({ setLog }: PageLogProps) {
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

  const selectedMetas = useMemo(
    () => factors.filter((f) => selected.has(f.name)),
    [factors, selected]
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
          setLog("默认副图超过 6，已截取前 6 个");
        }
      }
    } catch (error) {
      setLog(String(error));
    }
  }, [setLog]);

  /**
   * 按当前勾选与区间拉取因子序列。
   */
  const loadSeries = useCallback(async () => {
    if (!symbol.trim() || selected.size === 0) {
      setSeries(null);
      setSeriesError(null);
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
      setSeries(data);
    } catch (error) {
      setSeries(null);
      setSeriesError(String(error));
      setLog(String(error));
    } finally {
      setLoading(false);
    }
  }, [symbol, selected, range, setLog]);

  useEffect(() => {
    void refreshMeta();
  }, [refreshMeta]);

  useEffect(() => {
    if (!catalogReady.current) return;
    const timer = window.setTimeout(() => {
      void loadSeries();
    }, 300);
    return () => window.clearTimeout(timer);
  }, [loadSeries]);

  /**
   * 切换因子勾选；副图超过上限时拒绝并写日志。
   * @param name 因子 name
   */
  const onToggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
        return next;
      }
      const meta = factors.find((f) => f.name === name);
      if (meta?.plot === "panel") {
        const panelCount = [...next].filter((n) => {
          const m = factors.find((f) => f.name === n);
          return m?.plot === "panel";
        }).length;
        if (panelCount >= PANEL_LIMIT) {
          setLog(`副图最多勾选 ${PANEL_LIMIT} 个，请先取消部分 panel 因子`);
          return prev;
        }
      }
      next.add(name);
      return next;
    });
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
      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <FactorCatalog
          factors={factors}
          selected={selected}
          onToggle={onToggle}
          query={query}
          onQuery={setQuery}
        />
        <div className="space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] p-4">
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
            <Button variant="primary" onPress={() => void loadSeries()} isDisabled={loading}>
              {loading ? "计算中…" : "计算"}
            </Button>
            {series?.engine && (
              <span className="text-xs text-[var(--desk-mist)]">engine: {series.engine}</span>
            )}
          </div>
          {seriesError && (
            <p className="text-sm text-red-400">{seriesError}</p>
          )}
          <FactorCharts data={series} metas={selectedMetas} />
        </div>
      </div>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">模型</CardTitle>
          <div className="flex gap-2">
            <Button variant="primary" onPress={() => void trainBoth()}>
              LGBM vs XGB 对比训练
            </Button>
            <Button variant="secondary" onPress={() => void refreshMeta()}>
              刷新
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">
            {JSON.stringify(models, null, 2)}
          </pre>
          {comparison !== null && (
            <>
              <CardTitle className="text-base text-[var(--desk-text)]">引擎对比</CardTitle>
              <pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">
                {JSON.stringify(comparison, null, 2)}
              </pre>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
