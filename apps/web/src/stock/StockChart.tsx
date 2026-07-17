import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import { buildIntradayAvgSeries, buildSmaSeries, DAILY_MA_LINES, toChartBars } from "./format";
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
        textColor: "#ffffff",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.12)" },
        horzLines: { color: "rgba(255, 255, 255, 0.12)" },
      },
      rightPriceScale: { borderColor: "#ffffff" },
      timeScale: { borderColor: "#ffffff", timeVisible: period === "intraday" },
    });

    if (period === "intraday") {
      const series = chart.addSeries(AreaSeries, {
        lineColor: "#ef4444",
        topColor: "rgba(239, 68, 68, 0.35)",
        bottomColor: "rgba(239, 68, 68, 0.02)",
      });
      series.setData(chartBars.map(({ time, value }) => ({ time, value })));

      const avgPoints = buildIntradayAvgSeries(bars);
      if (avgPoints.length > 0) {
        const avgSeries = chart.addSeries(LineSeries, {
          color: "#f59e0b",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        avgSeries.setData(avgPoints);
      }
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

      if (period === "day") {
        for (const ma of DAILY_MA_LINES) {
          const points = buildSmaSeries(chartBars, ma.window);
          if (points.length === 0) continue;
          const maSeries = chart.addSeries(LineSeries, {
            color: ma.color,
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          maSeries.setData(points);
        }
      }
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
  }, [bars, chartBars, compact, period]);

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
