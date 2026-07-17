import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import {
  ASHARE_SESSION_LAST_INDEX,
  buildIntradayAvgSeries,
  buildIntradaySessionPlaceholders,
  buildSmaSeries,
  DAILY_MA_LINES,
  formatIntradayTickMark,
  toChartBars,
} from "./format";
import type { ChartPeriod, OhlcvBar } from "./types";

export type StockChartProps = {
  period: ChartPeriod;
  bars: OhlcvBar[];
  compact?: boolean;
};

const INTRADAY_TIME_BASE = 1_000_000;

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
      localization:
        period === "intraday"
          ? {
              timeFormatter: (time) => formatIntradayTickMark(time),
            }
          : undefined,
      timeScale: {
        borderColor: "#ffffff",
        timeVisible: period === "intraday",
        secondsVisible: false,
        tickMarkFormatter:
          period === "intraday" ? (time) => formatIntradayTickMark(time) : undefined,
      },
    });

    if (period === "intraday") {
      const series = chart.addSeries(AreaSeries, {
        lineColor: "#ef4444",
        topColor: "rgba(239, 68, 68, 0.35)",
        bottomColor: "rgba(239, 68, 68, 0.02)",
        lastValueVisible: false,
        priceLineVisible: false,
      });

      // 先铺全天占位，保证 09:30 / 11:30·13:00 / 15:00 刻度一定落在轴上
      const placeholders = buildIntradaySessionPlaceholders();
      const valueByTime = new Map(chartBars.map((bar) => [Number(bar.time), bar.value]));
      series.setData(
        placeholders.map((point) => {
          const value = valueByTime.get(Number(point.time));
          return value == null ? point : { time: point.time, value };
        })
      );

      const avgPoints = buildIntradayAvgSeries(bars);
      if (avgPoints.length > 0) {
        const avgSeries = chart.addSeries(LineSeries, {
          color: "#f59e0b",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        const avgByTime = new Map(avgPoints.map((p) => [Number(p.time), p.value]));
        avgSeries.setData(
          placeholders.map((point) => {
            const value = avgByTime.get(Number(point.time));
            return value == null ? point : { time: point.time, value };
          })
        );
      }

      chart.timeScale().setVisibleRange({
        from: (INTRADAY_TIME_BASE + 0) as UTCTimestamp,
        to: (INTRADAY_TIME_BASE + ASHARE_SESSION_LAST_INDEX) as UTCTimestamp,
      });
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

      chart.timeScale().fitContent();
    }

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
