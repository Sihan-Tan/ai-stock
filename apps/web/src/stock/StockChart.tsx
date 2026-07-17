import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ASHARE_CONTINUOUS_START_INDEX,
  ASHARE_SESSION_LAST_INDEX,
  buildIntradayAvgSeries,
  buildIntradaySessionPlaceholders,
  buildMacdSeries,
  buildSmaSeries,
  type ChartBar,
  DAILY_MA_LINES,
  formatDailyCrosshairTime,
  formatIntradayCrosshairTime,
  formatIntradayTickMark,
  MACD_LINE_COLORS,
  toChartBars,
} from "./format";
import type { ChartPeriod, OhlcvBar } from "./types";

export type StockChartProps = {
  period: ChartPeriod;
  bars: OhlcvBar[];
  compact?: boolean;
};

const INTRADAY_TIME_BASE = 1_000_000;

type HoverPriceLabel = {
  x: number;
  y: number;
  text: string;
};

/**
 * 在副图区域叠加成交量柱。
 * @param chart 图表实例
 * @param chartBars K 线数据
 * @param withMacd 下方是否还要留 MACD 区域
 */
function addVolumePane(chart: IChartApi, chartBars: ChartBar[], withMacd: boolean): void {
  const volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
    lastValueVisible: false,
    priceLineVisible: false,
  });
  volumeSeries.priceScale().applyOptions({
    scaleMargins: withMacd ? { top: 0.58, bottom: 0.24 } : { top: 0.78, bottom: 0 },
    borderVisible: false,
  });
  volumeSeries.setData(
    chartBars.map((bar) => ({
      time: bar.time,
      value: Number(bar.volume ?? 0),
      color: bar.close >= bar.open ? "rgba(239, 68, 68, 0.45)" : "rgba(34, 197, 94, 0.45)",
    }))
  );
}

/**
 * 在副图区域叠加 MACD（柱 + DIF + DEA）。
 * @param chart 图表实例
 * @param chartBars K 线数据
 */
function addMacdPane(chart: IChartApi, chartBars: ChartBar[]): void {
  const macdPoints = buildMacdSeries(chartBars);
  if (macdPoints.length === 0) {
    return;
  }

  const histSeries = chart.addSeries(HistogramSeries, {
    priceScaleId: "macd",
    lastValueVisible: false,
    priceLineVisible: false,
  });
  histSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
    borderVisible: false,
  });
  histSeries.setData(
    macdPoints.map((point) => ({
      time: point.time,
      value: point.hist,
      color: point.hist >= 0 ? "rgba(239, 68, 68, 0.55)" : "rgba(34, 197, 94, 0.55)",
    }))
  );

  const difSeries = chart.addSeries(LineSeries, {
    color: MACD_LINE_COLORS.dif,
    lineWidth: 1,
    priceScaleId: "macd",
    lastValueVisible: false,
    priceLineVisible: false,
    crosshairMarkerVisible: false,
  });
  difSeries.setData(macdPoints.map((point) => ({ time: point.time, value: point.dif })));

  const deaSeries = chart.addSeries(LineSeries, {
    color: MACD_LINE_COLORS.dea,
    lineWidth: 1,
    priceScaleId: "macd",
    lastValueVisible: false,
    priceLineVisible: false,
    crosshairMarkerVisible: false,
  });
  deaSeries.setData(macdPoints.map((point) => ({ time: point.time, value: point.dea })));
}

/**
 * 从主图序列数据点取出展示价格。
 * @param data 十字光标命中的序列数据
 */
function readSeriesPrice(data: unknown): number | null {
  if (!data || typeof data !== "object") {
    return null;
  }
  const row = data as { close?: number; value?: number };
  if (typeof row.close === "number" && Number.isFinite(row.close)) {
    return row.close;
  }
  if (typeof row.value === "number" && Number.isFinite(row.value)) {
    return row.value;
  }
  return null;
}

/**
 * 格式化悬浮价格文本。
 * @param price 价格
 */
function formatHoverPrice(price: number): string {
  return price.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * 根据行情周期渲染分时走势或日周月 K 线图。
 * @param props 图表周期、数据与紧凑展示选项
 */
export function StockChart({ period, bars, compact = false }: StockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const auctionBandRef = useRef<HTMLDivElement>(null);
  const auctionLineRef = useRef<HTMLDivElement>(null);
  const [hoverLabel, setHoverLabel] = useState<HoverPriceLabel | null>(null);
  const chartBars = useMemo(() => toChartBars(bars, period), [bars, period]);
  const showVolume =
    period === "intraday" || period === "day" || period === "week" || period === "month";
  const showMacd = period === "intraday" || period === "day";
  const chartHeight = showMacd
    ? compact
      ? 300
      : 400
    : showVolume
      ? compact
        ? 240
        : 320
      : compact
        ? 192
        : 256;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || chartBars.length === 0) {
      return;
    }

    setHoverLabel(null);

    const chart = createChart(container, {
      width: container.clientWidth,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#ffffff",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.12)" },
        horzLines: { color: "rgba(255, 255, 255, 0.12)" },
      },
      rightPriceScale: {
        borderColor: "#ffffff",
        scaleMargins: showMacd
          ? { top: 0.06, bottom: 0.46 }
          : showVolume
            ? { top: 0.08, bottom: 0.28 }
            : { top: 0.1, bottom: 0.1 },
      },
      crosshair: {
        // 价格改由主图线旁浮层展示，不再贴右侧坐标轴
        horzLine: {
          labelVisible: false,
        },
        vertLine: {
          labelVisible: true,
        },
      },
      localization: {
        timeFormatter:
          period === "intraday"
            ? (time: Time) => formatIntradayCrosshairTime(time)
            : period === "day"
              ? (time: Time) => formatDailyCrosshairTime(time)
              : undefined,
      },
      timeScale: {
        borderColor: "#ffffff",
        timeVisible: period === "intraday",
        secondsVisible: false,
        tickMarkFormatter:
          period === "intraday" ? (time: Time) => formatIntradayTickMark(time) : undefined,
      },
    });

    let mainSeries: ISeriesApi<"Area"> | ISeriesApi<"Candlestick">;

    if (period === "intraday") {
      const series = chart.addSeries(AreaSeries, {
        lineColor: "#ef4444",
        topColor: "rgba(239, 68, 68, 0.35)",
        bottomColor: "rgba(239, 68, 68, 0.02)",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      mainSeries = series;

      // 先铺全天占位，保证 09:15 / 09:30 / 11:30·13:00 / 15:00 刻度一定落在轴上
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

      if (showVolume) {
        addVolumePane(chart, chartBars, showMacd);
      }
      if (showMacd) {
        addMacdPane(chart, chartBars);
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
        lastValueVisible: false,
      });
      mainSeries = series;
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

      if (showVolume) {
        addVolumePane(chart, chartBars, showMacd);
      }
      if (showMacd) {
        addMacdPane(chart, chartBars);
      }

      chart.timeScale().fitContent();
    }

    const syncAuctionOverlay = () => {
      if (period !== "intraday") {
        return;
      }

      const x0 = chart.timeScale().timeToCoordinate((INTRADAY_TIME_BASE + 0) as Time);
      const x1 = chart
        .timeScale()
        .timeToCoordinate((INTRADAY_TIME_BASE + ASHARE_CONTINUOUS_START_INDEX) as Time);

      if (auctionBandRef.current) {
        auctionBandRef.current.style.display = x0 == null || x1 == null ? "none" : "block";
      }
      if (auctionLineRef.current) {
        auctionLineRef.current.style.display = x0 == null || x1 == null ? "none" : "block";
      }
      if (x0 == null || x1 == null) {
        return;
      }
      if (auctionBandRef.current) {
        auctionBandRef.current.style.left = `${x0}px`;
        auctionBandRef.current.style.width = `${Math.max(0, x1 - x0)}px`;
      }
      if (auctionLineRef.current) {
        auctionLineRef.current.style.left = `${x1}px`;
      }
    };
    syncAuctionOverlay();
    chart.timeScale().subscribeVisibleLogicalRangeChange(syncAuctionOverlay);

    const onCrosshairMove = (param: {
      point?: { x: number; y: number } | undefined;
      time?: Time;
      seriesData: Map<unknown, unknown>;
    }) => {
      if (!param.point || param.time === undefined) {
        setHoverLabel(null);
        return;
      }
      const price = readSeriesPrice(param.seriesData.get(mainSeries));
      if (price == null) {
        setHoverLabel(null);
        return;
      }
      const y = mainSeries.priceToCoordinate(price);
      if (y == null) {
        setHoverLabel(null);
        return;
      }
      setHoverLabel({
        x: param.point.x,
        y,
        text: formatHoverPrice(price),
      });
    };
    chart.subscribeCrosshairMove(onCrosshairMove);

    const resizeObserver = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: entry.contentRect.width });
      syncAuctionOverlay();
    });
    resizeObserver.observe(container);

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(syncAuctionOverlay);
      chart.unsubscribeCrosshairMove(onCrosshairMove);
      resizeObserver.disconnect();
      chart.remove();
      setHoverLabel(null);
    };
  }, [bars, chartBars, chartHeight, period, showMacd, showVolume]);

  const heightClass = showMacd
    ? compact
      ? "h-[300px]"
      : "h-[400px]"
    : showVolume
      ? compact
        ? "h-60"
        : "h-80"
      : compact
        ? "h-48"
        : "h-64";

  if (chartBars.length === 0) {
    return (
      <div
        className={`flex w-full items-center justify-center rounded-md border border-dashed border-[var(--desk-line)] text-sm text-[var(--desk-mist)] ${heightClass}`}
      >
        暂无行情数据
      </div>
    );
  }

  return (
    <div className={`relative w-full ${heightClass}`}>
      {period === "intraday" && (
        <>
          <div
            ref={auctionBandRef}
            className="pointer-events-none absolute inset-y-0 z-0"
            style={{ backgroundColor: "rgba(148, 163, 184, 0.12)" }}
          />
          <div
            ref={auctionLineRef}
            className="pointer-events-none absolute inset-y-0 z-0 w-px"
            style={{ backgroundColor: "rgba(148, 163, 184, 0.55)" }}
          />
        </>
      )}
      <div ref={containerRef} className="absolute inset-0 z-10 w-full" />
      {hoverLabel && (
        <div
          className="pointer-events-none absolute z-10 -translate-y-1/2 rounded px-1.5 py-0.5 font-mono text-xs text-white shadow"
          style={{
            left: hoverLabel.x + 10,
            top: hoverLabel.y,
            backgroundColor: "rgba(15, 23, 42, 0.88)",
            border: "1px solid rgba(255, 255, 255, 0.2)",
          }}
        >
          {hoverLabel.text}
        </div>
      )}
    </div>
  );
}
