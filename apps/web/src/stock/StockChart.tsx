import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  createChart,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import { toChartBars } from "./format";
import type { ChartPeriod, OhlcvBar } from "./types";

export type StockChartProps = {
  period: ChartPeriod;
  bars: OhlcvBar[];
  compact?: boolean;
};

/**
 * 根据行情周期渲染分时走势或日周月 K 线图。
 * @param props 图表周期、数据与紧凑展示选项
 */
export function StockChart({ period, bars, compact = false }: StockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartBars = useMemo(() => toChartBars(bars, period), [bars, period]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || chartBars.length === 0) {
      return;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: compact ? 192 : 256,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "var(--desk-mist)",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.15)" },
        horzLines: { color: "rgba(148, 163, 184, 0.15)" },
      },
      rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.25)" },
      timeScale: { borderColor: "rgba(148, 163, 184, 0.25)", timeVisible: period === "intraday" },
    });

    if (period === "intraday") {
      const series = chart.addSeries(AreaSeries, {
        lineColor: "#ef4444",
        topColor: "rgba(239, 68, 68, 0.35)",
        bottomColor: "rgba(239, 68, 68, 0.02)",
      });
      series.setData(chartBars.map(({ time, value }) => ({ time, value })));
    } else {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#ef4444",
        downColor: "#22c55e",
        borderVisible: false,
        wickUpColor: "#ef4444",
        wickDownColor: "#22c55e",
      });
      series.setData(
        chartBars.map(({ time, open, high, low, close }) => ({
          time,
          open,
          high,
          low,
          close,
        }))
      );
    }

    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: entry.contentRect.width });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [chartBars, compact, period]);

  if (chartBars.length === 0) {
    return (
      <div
        className={`flex w-full items-center justify-center rounded-md border border-dashed border-[var(--desk-line)] text-sm text-[var(--desk-mist)] ${
          compact ? "h-48" : "h-64"
        }`}
      >
        暂无行情数据
      </div>
    );
  }

  return <div ref={containerRef} className={compact ? "h-48 w-full" : "h-64 w-full"} />;
}
