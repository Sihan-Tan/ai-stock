import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  createTextWatermark,
  type IChartApi,
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
/** 时间轴预留高度 */
const TIME_AXIS_HEIGHT = 28;
/** 右侧价格轴统一最小宽度（多 pane 仍会再取各轴 max） */
const PRICE_SCALE_MIN_WIDTH = 80;

/**
 * 将日期字符串转为 lightweight-charts 时间（优先业务日）。
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
 * 按主图 bars 的日期对齐因子序列：无效值用 whitespace，保证与 K 线一一对应。
 * @param barDates 主图日期列表（已规范化）
 * @param points 因子点
 */
function toAlignedLineData(
  barDates: string[],
  points: FactorPoint[]
): ({ time: Time; value: number } | { time: Time })[] {
  const byDate = new Map<string, number | null>();
  for (const p of points) {
    byDate.set(p.date.slice(0, 10), p.v);
  }
  const out: ({ time: Time; value: number } | { time: Time })[] = [];
  for (const date of barDates) {
    const time = toChartTime(date);
    if (time == null) continue;
    const v = byDate.get(date);
    if (v == null || !Number.isFinite(v)) {
      out.push({ time });
    } else {
      out.push({ time, value: v });
    }
  }
  return out;
}

/**
 * 将各 pane 右侧价格轴拉到同一宽度（库本身会取 max，这里再显式加固一次）。
 * @param chart 图表
 */
function syncPanePriceScaleWidths(chart: IChartApi): void {
  let maxWidth = PRICE_SCALE_MIN_WIDTH;
  for (const pane of chart.panes()) {
    maxWidth = Math.max(maxWidth, pane.priceScale("right").width());
  }
  chart.applyOptions({
    rightPriceScale: { minimumWidth: maxWidth },
  });
  for (const pane of chart.panes()) {
    pane.priceScale("right").applyOptions({ minimumWidth: maxWidth });
  }
}

/**
 * 主图 + 副图：同一 chart 多 pane，共用时间轴；右侧轴宽由库按各 pane 取 max 对齐。
 * @param props 序列数据与勾选元数据
 */
export function FactorCharts({ data, metas }: FactorChartsProps) {
  const hostRef = useRef<HTMLDivElement>(null);

  const overlayMetas = useMemo(
    () => metas.filter((m) => m.plot === "overlay"),
    [metas]
  );
  const panelMetas = useMemo(
    () => metas.filter((m) => m.plot === "panel"),
    [metas]
  );

  const separatorExtra = Math.max(0, panelMetas.length); // pane 之间分隔线
  const totalHeight =
    MAIN_HEIGHT + panelMetas.length * PANEL_HEIGHT + TIME_AXIS_HEIGHT + separatorExtra;

  useEffect(() => {
    const host = hostRef.current;
    if (!data || data.bars.length === 0 || !host) {
      return;
    }

    // HMR / 严格模式重跑时清掉残留 DOM，避免叠两套图
    host.replaceChildren();

    const barDates = data.bars.map((b) => b.date.slice(0, 10));
    let disposed = false;

    const chart = createChart(host, {
      autoSize: true,
      width: host.clientWidth || undefined,
      height: totalHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(232, 236, 244, 0.72)",
        attributionLogo: true,
        panes: {
          enableResize: false,
          separatorColor: "rgba(255, 255, 255, 0.14)",
          separatorHoverColor: "rgba(255, 255, 255, 0.22)",
        },
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.08)" },
        horzLines: { color: "rgba(255, 255, 255, 0.08)" },
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.12)",
        scaleMargins: { top: 0.08, bottom: 0.08 },
        minimumWidth: PRICE_SCALE_MIN_WIDTH,
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.12)",
        visible: true,
        timeVisible: false,
        secondsVisible: false,
      },
      crosshair: {
        horzLine: { labelVisible: true },
        vertLine: { labelVisible: true },
      },
    });

    const mainPane = chart.panes()[0];
    mainPane.setStretchFactor(MAIN_HEIGHT);

    const candle = mainPane.addSeries(CandlestickSeries, {
      upColor: "#ef4444",
      downColor: "#22c55e",
      borderVisible: false,
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
      lastValueVisible: false,
      priceScaleId: "right",
    });
    candle.setData(
      data.bars.flatMap((bar) => {
        const time = toChartTime(bar.date.slice(0, 10));
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
        const series = mainPane.addSeries(LineSeries, {
          color: OVERLAY_COLORS[colorIdx % OVERLAY_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          priceScaleId: "right",
        });
        colorIdx += 1;
        series.setData(toAlignedLineData(barDates, points));
      }
    }

    for (const meta of panelMetas) {
      const pane = chart.addPane(true);
      pane.setStretchFactor(PANEL_HEIGHT);
      createTextWatermark(pane, {
        horzAlign: "left",
        vertAlign: "top",
        lines: [
          {
            text: meta.label || meta.name,
            color: "rgba(232, 236, 244, 0.55)",
            fontSize: 11,
          },
        ],
      });
      pane.priceScale("right").applyOptions({
        borderColor: "rgba(255, 255, 255, 0.12)",
        scaleMargins: { top: 0.12, bottom: 0.12 },
        minimumWidth: PRICE_SCALE_MIN_WIDTH,
      });

      const outputs = data.series[meta.name]?.outputs ?? {};
      const isMacd =
        meta.name.toUpperCase() === "MACD" ||
        meta.name.toUpperCase().startsWith("MACD") ||
        meta.outputs.some((o) => o.includes("hist"));

      if (isMacd) {
        const histKey = meta.outputs.find((o) => o.includes("hist")) ?? "macd_hist";
        const histPoints = outputs[histKey];
        if (histPoints?.length) {
          const histSeries = pane.addSeries(HistogramSeries, {
            lastValueVisible: false,
            priceLineVisible: false,
            priceScaleId: "right",
          });
          histSeries.setData(
            toAlignedLineData(barDates, histPoints).map((p) => {
              if (!("value" in p)) return p;
              return {
                ...p,
                color: p.value >= 0 ? "rgba(239, 68, 68, 0.55)" : "rgba(34, 197, 94, 0.55)",
              };
            })
          );
        }
        let lineColorIdx = 0;
        for (const outName of meta.outputs) {
          if (outName.includes("hist")) continue;
          const points = outputs[outName];
          if (!points?.length) continue;
          const line = pane.addSeries(LineSeries, {
            color: lineColorIdx === 0 ? "#fbbf24" : "#38bdf8",
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
            priceScaleId: "right",
          });
          lineColorIdx += 1;
          line.setData(toAlignedLineData(barDates, points));
        }
      } else {
        let lineColorIdx = 0;
        for (const outName of meta.outputs) {
          const points = outputs[outName];
          if (!points?.length) continue;
          const line = pane.addSeries(LineSeries, {
            color: OVERLAY_COLORS[lineColorIdx % OVERLAY_COLORS.length],
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
            priceScaleId: "right",
          });
          lineColorIdx += 1;
          line.setData(toAlignedLineData(barDates, points));
        }
      }
    }

    chart.timeScale().fitContent();

    const realign = () => {
      if (disposed) return;
      syncPanePriceScaleWidths(chart);
    };
    requestAnimationFrame(() => {
      realign();
      requestAnimationFrame(realign);
    });
    const t1 = window.setTimeout(realign, 50);
    const t2 = window.setTimeout(realign, 200);

    return () => {
      disposed = true;
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      chart.remove();
      host.replaceChildren();
    };
  }, [data, overlayMetas, panelMetas, totalHeight]);

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
    <div
      ref={hostRef}
      className="w-full"
      style={{ height: totalHeight }}
      data-factor-charts="multipane-v2"
      aria-label="因子主图与副图（单图多窗格）"
    />
  );
}
