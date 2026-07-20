import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type LogicalRange,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import type { FactorMeta, FactorPoint, FactorSeriesResponse } from "./types";

export type FactorChartsProps = {
  /** 序列响应；无数据时展示空态 */
  data: FactorSeriesResponse | null;
  /** 当前勾选的因子元数据 */
  metas: FactorMeta[];
};

const OVERLAY_COLORS = [
  "#fbbf24",
  "#38bdf8",
  "#a78bfa",
  "#f472b6",
  "#34d399",
  "#fb923c",
  "#e879f9",
  "#2dd4bf",
];

const PANEL_HEIGHT = 120;
const MAIN_HEIGHT = 320;

/**
 * 将日期字符串转为 lightweight-charts 时间（优先业务日，否则 UTC 秒）。
 * @param date API 日期
 */
function toChartTime(date: string): Time | null {
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return date;
  }
  const ms = Date.parse(date.includes("T") ? date : `${date}T00:00:00Z`);
  if (!Number.isFinite(ms)) return null;
  return Math.floor(ms / 1000) as UTCTimestamp;
}

/**
 * 将因子点转为折线/柱状数据（跳过 null）。
 * @param points 因子序列点
 */
function toLineData(points: FactorPoint[]): { time: Time; value: number }[] {
  const out: { time: Time; value: number }[] = [];
  for (const p of points) {
    if (p.v == null || !Number.isFinite(p.v)) continue;
    const time = toChartTime(p.date);
    if (time == null) continue;
    out.push({ time, value: p.v });
  }
  return out;
}

/**
 * 创建统一样式的图表实例。
 * @param container 挂载容器
 * @param height 高度
 */
function makeChart(container: HTMLElement, height: number): IChartApi {
  return createChart(container, {
    width: container.clientWidth,
    height,
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: "rgba(232, 236, 244, 0.72)",
    },
    grid: {
      vertLines: { color: "rgba(255, 255, 255, 0.08)" },
      horzLines: { color: "rgba(255, 255, 255, 0.08)" },
    },
    rightPriceScale: {
      borderColor: "rgba(255, 255, 255, 0.12)",
      scaleMargins: { top: 0.08, bottom: 0.08 },
    },
    timeScale: {
      borderColor: "rgba(255, 255, 255, 0.12)",
      timeVisible: false,
      secondsVisible: false,
    },
    crosshair: {
      horzLine: { labelVisible: true },
      vertLine: { labelVisible: true },
    },
  });
}

/**
 * 主图 + 副图：overlay 叠主图，每个 panel 因子独立 pane；主图时间范围同步到副图。
 * @param props 序列数据与勾选元数据
 */
export function FactorCharts({ data, metas }: FactorChartsProps) {
  const mainRef = useRef<HTMLDivElement>(null);
  const panelsHostRef = useRef<HTMLDivElement>(null);

  const overlayMetas = useMemo(
    () => metas.filter((m) => m.plot === "overlay"),
    [metas]
  );
  const panelMetas = useMemo(
    () => metas.filter((m) => m.plot === "panel"),
    [metas]
  );

  useEffect(() => {
    const mainEl = mainRef.current;
    const panelsHost = panelsHostRef.current;
    if (!data || data.bars.length === 0 || !mainEl) {
      return;
    }

    const charts: IChartApi[] = [];
    const resizeObservers: ResizeObserver[] = [];

    const mainChart = makeChart(mainEl, MAIN_HEIGHT);
    charts.push(mainChart);

    const candle = mainChart.addSeries(CandlestickSeries, {
      upColor: "#ef4444",
      downColor: "#22c55e",
      borderVisible: false,
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
      lastValueVisible: false,
    });
    candle.setData(
      data.bars.flatMap((bar) => {
        const time = toChartTime(bar.date);
        if (time == null) return [];
        return [{ time, open: bar.o, high: bar.h, low: bar.l, close: bar.c }];
      })
    );

    let colorIdx = 0;
    for (const meta of overlayMetas) {
      const outputs = data.series[meta.name]?.outputs ?? {};
      for (const outName of meta.outputs) {
        const points = outputs[outName];
        if (!points?.length) continue;
        const series = mainChart.addSeries(LineSeries, {
          color: OVERLAY_COLORS[colorIdx % OVERLAY_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        colorIdx += 1;
        series.setData(toLineData(points));
      }
    }

    mainChart.timeScale().fitContent();

    const panelCharts: IChartApi[] = [];

    /**
     * 监听容器宽度变化并同步图表宽度。
     * @param el 容器
     * @param chart 图表
     */
    const observeWidth = (el: HTMLElement, chart: IChartApi) => {
      const ro = new ResizeObserver(([entry]) => {
        chart.applyOptions({ width: entry.contentRect.width });
      });
      ro.observe(el);
      resizeObservers.push(ro);
    };
    observeWidth(mainEl, mainChart);

    if (panelsHost) {
      for (const meta of panelMetas) {
        const el = panelsHost.querySelector<HTMLElement>(`[data-panel="${meta.name}"]`);
        if (!el) continue;
        const panelChart = makeChart(el, PANEL_HEIGHT);
        charts.push(panelChart);
        panelCharts.push(panelChart);
        observeWidth(el, panelChart);

        const outputs = data.series[meta.name]?.outputs ?? {};
        const isMacd =
          meta.name.toUpperCase() === "MACD" ||
          meta.outputs.some((o) => o.includes("hist"));

        if (isMacd) {
          const histKey =
            meta.outputs.find((o) => o.includes("hist")) ?? "macd_hist";
          const histPoints = outputs[histKey];
          if (histPoints?.length) {
            const histSeries = panelChart.addSeries(HistogramSeries, {
              lastValueVisible: false,
              priceLineVisible: false,
            });
            histSeries.setData(
              toLineData(histPoints).map((p) => ({
                ...p,
                color: p.value >= 0 ? "rgba(239, 68, 68, 0.55)" : "rgba(34, 197, 94, 0.55)",
              }))
            );
          }
          let lineColorIdx = 0;
          for (const outName of meta.outputs) {
            if (outName.includes("hist")) continue;
            const points = outputs[outName];
            if (!points?.length) continue;
            const line = panelChart.addSeries(LineSeries, {
              color: lineColorIdx === 0 ? "#fbbf24" : "#38bdf8",
              lineWidth: 1,
              priceLineVisible: false,
              lastValueVisible: false,
              crosshairMarkerVisible: false,
            });
            lineColorIdx += 1;
            line.setData(toLineData(points));
          }
        } else {
          let lineColorIdx = 0;
          for (const outName of meta.outputs) {
            const points = outputs[outName];
            if (!points?.length) continue;
            const line = panelChart.addSeries(LineSeries, {
              color: OVERLAY_COLORS[lineColorIdx % OVERLAY_COLORS.length],
              lineWidth: 1,
              priceLineVisible: false,
              lastValueVisible: false,
              crosshairMarkerVisible: false,
            });
            lineColorIdx += 1;
            line.setData(toLineData(points));
          }
        }

        panelChart.timeScale().fitContent();
      }
    }

    const syncPanels = (range: LogicalRange | null) => {
      if (!range) return;
      for (const panel of panelCharts) {
        panel.timeScale().setVisibleLogicalRange(range);
      }
    };
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(syncPanels);
    syncPanels(mainChart.timeScale().getVisibleLogicalRange());

    return () => {
      mainChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncPanels);
      for (const ro of resizeObservers) ro.disconnect();
      for (const chart of charts) chart.remove();
    };
  }, [data, overlayMetas, panelMetas]);

  if (!data) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-md border border-dashed border-[var(--desk-line)] text-sm text-[var(--desk-mist)]">
        选择标的并计算后展示图表
      </div>
    );
  }

  if (data.bars.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-md border border-dashed border-[var(--desk-line)] text-sm text-[var(--desk-mist)]">
        暂无行情数据
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        ref={mainRef}
        className="w-full"
        style={{ height: MAIN_HEIGHT }}
        aria-label="因子主图"
      />
      <div ref={panelsHostRef} className="space-y-2">
        {panelMetas.map((meta) => (
          <div key={meta.name}>
            <div className="mb-0.5 text-xs text-[var(--desk-mist)]">{meta.label}</div>
            <div
              data-panel={meta.name}
              className="w-full"
              style={{ height: PANEL_HEIGHT }}
              aria-label={`${meta.label} 副图`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
