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

  const dailyMaLegend = useMemo(() => {
    if (period !== "day" || chartBars.length === 0) return [];
    return DAILY_MA_LINES.map((ma) => {
      const points = buildSmaSeries(chartBars, ma.window);
      const latest = points.length > 0 ? points[points.length - 1].value : null;
      return { ...ma, value: latest };
    });
  }, [chartBars, period]);

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

  return (
    <div className="space-y-2">
      {dailyMaLegend.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {dailyMaLegend.map((ma) => (
            <span key={ma.label} className="inline-flex items-center gap-1.5 font-mono">
              <span className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: ma.color }} />
              <span style={{ color: ma.color }}>
                {ma.label} {formatMaPrice(ma.value)}
              </span>
            </span>
          ))}
        </div>
      )}
      <div ref={containerRef} className={compact ? "h-48 w-full" : "h-64 w-full"} />
    </div>
  );
}

/**
 * 格式化均线最新价展示。
 * @param value 均线数值
 */
function formatMaPrice(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
