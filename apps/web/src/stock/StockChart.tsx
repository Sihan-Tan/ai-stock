import {
  AreaSeries,
  BarSeries,
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildIntradayAvgSeries,
  buildMacdSeries,
  type ChartBar,
  formatDailyCrosshairTime,
  formatIntradayCrosshairTime,
  formatIntradayTickMark,
  MACD_LINE_COLORS,
  toChartBars,
} from "./format";
import { buildIntradayFundFlow } from "./intradayFundFlow";
import {
  ashareContinuousStartSlot,
  ashareSessionLastSlot,
  buildIntradaySlotPlaceholders,
  INTRADAY_TIME_BASE,
  mapMinuteBarsToSlots,
} from "./intradaySlots";
import {
  buildMainOverlay,
  getMainOverlay,
  INTRADAY_DIP_SHOW_STRENGTH_BANDS,
} from "./mainOverlays";
import type { ChartPeriod, OhlcvBar } from "./types";

/** 分时色带/信号竖条按颜色拆组；强弱色带受 {@link INTRADAY_DIP_SHOW_STRENGTH_BANDS} 控制。 */
const INTRADAY_STICK_COLORS = [
  ...(INTRADAY_DIP_SHOW_STRENGTH_BANDS ? (["#0000FF", "#00FF00"] as const) : []),
  "#EAB308",
] as const;

export type StockChartProps = {
  period: ChartPeriod;
  bars: OhlcvBar[];
  compact?: boolean;
  /** 主图指标族 id；日线默认 sma，分时默认由调用方传入（如 none / intraday_dip） */
  mainOverlayId?: string;
  /** 分时槽宽（秒）；默认 60 兼容旧分钟轴 */
  slotSec?: number;
  /** 父组件已合并的分时槽序列（分钟映射 + 报价补点）；优先于内部 map */
  intradayChartBars?: ChartBar[];
  /** 分时叠加计算用的原始分钟线（可含预热日）；仅 period=intraday 时使用 */
  overlayCalcBars?: OhlcvBar[];
  /** 资金趋势用个股序列（预热非当日 + 当日槽伪 OHLCV）；缺省回退 overlayCalcBars/bars */
  fundStockBars?: OhlcvBar[];
  /** 昨收价；分时抄底等指标的基准价 */
  preClose?: number | null;
  /** 当天会话日期 YYYY-MM-DD（北京）；用于从 calcBars 截取当日 */
  sessionDate?: string;
  /** 指数分钟线（含预热）；分时资金趋势副图用 */
  indexBars?: OhlcvBar[];
};

/**
 * 将分钟轴伪时间重映射到槽轴伪时间。
 * @param time 分钟轴时间
 * @param slotSec 槽宽
 */
function remapMinuteChartTimeToSlot(time: Time, slotSec: number): UTCTimestamp {
  const width = Math.max(1, Math.floor(slotSec));
  if (width === 60) {
    return time as UTCTimestamp;
  }
  const minuteIndex = Number(time) - INTRADAY_TIME_BASE;
  const slotIndex = Math.floor((minuteIndex * 60) / width);
  return (INTRADAY_TIME_BASE + slotIndex) as UTCTimestamp;
}

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
 * @param withFundFlow 下方是否还要留资金趋势区域（分时四 pane）
 */
function addVolumePane(
  chart: IChartApi,
  chartBars: ChartBar[],
  withMacd: boolean,
  withFundFlow = false
): void {
  const volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
    lastValueVisible: false,
    priceLineVisible: false,
  });
  volumeSeries.priceScale().applyOptions({
    scaleMargins: withFundFlow
      ? { top: 0.52, bottom: 0.38 }
      : withMacd
        ? { top: 0.58, bottom: 0.24 }
        : { top: 0.78, bottom: 0 },
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
 * @param withFundFlow 下方是否还要留资金趋势区域（分时四 pane）
 */
function addMacdPane(chart: IChartApi, chartBars: ChartBar[], withFundFlow = false): void {
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
    scaleMargins: withFundFlow ? { top: 0.66, bottom: 0.22 } : { top: 0.8, bottom: 0 },
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
 * 在副图区域叠加分时「资金趋势」（柱 + 趋势线 + 信号竖条/标记）。
 * @param chart 图表实例
 * @param stockBars 个股分钟线（可含预热）
 * @param indexBars 指数分钟线（可含预热；可空）
 * @param sessionDate 当天 YYYY-MM-DD（北京）；缺省则不绘制
 * @param slotSec 槽宽（秒）
 */
function addFundFlowPane(
  chart: IChartApi,
  stockBars: OhlcvBar[],
  indexBars: OhlcvBar[] | undefined,
  sessionDate: string | undefined,
  slotSec?: number
): void {
  if (!sessionDate) {
    return;
  }

  const built = buildIntradayFundFlow({
    stockBars,
    indexBars: indexBars ?? [],
    sessionDate,
    slotSec,
  });

  const histByColor = new Map<string, Array<{ time: Time; value: number; color: string }>>();
  for (const hist of built.hists) {
    const group = histByColor.get(hist.color) ?? [];
    group.push({ time: hist.time, value: hist.value, color: hist.color });
    histByColor.set(hist.color, group);
  }
  for (const [color, points] of histByColor) {
    const histSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "fund",
      lastValueVisible: false,
      priceLineVisible: false,
      color,
    });
    histSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      borderVisible: false,
    });
    histSeries.setData(points);
  }

  const trendLine = built.lines.find((line) => line.label === "趋势线") ?? built.lines[0];
  const trendSeries = chart.addSeries(LineSeries, {
    color: trendLine?.color ?? "#F8FAFC",
    lineWidth: 1,
    priceScaleId: "fund",
    lastValueVisible: false,
    priceLineVisible: false,
    crosshairMarkerVisible: false,
  });
  trendSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.82, bottom: 0 },
    borderVisible: false,
  });
  if (trendLine && trendLine.points.length > 0) {
    trendSeries.setData(trendLine.points);
  }

  const stickColors = [...new Set(built.sticks.map((stick) => stick.color))];
  for (const color of stickColors) {
    const sticks = built.sticks.filter((stick) => stick.color === color);
    if (sticks.length === 0) continue;
    const stickSeries = chart.addSeries(BarSeries, {
      upColor: color,
      downColor: color,
      thinBars: true,
      openVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      priceScaleId: "fund",
    });
    stickSeries.setData(
      sticks.map((stick) => ({
        time: stick.time,
        open: stick.low,
        high: stick.high,
        low: stick.low,
        close: stick.high,
      }))
    );
  }

  if (built.markers.length > 0) {
    createSeriesMarkers(
      trendSeries,
      [...built.markers]
        .sort((a, b) => Number(a.time) - Number(b.time))
        .map((marker) => ({
          time: marker.time,
          position: "atPriceMiddle" as const,
          shape: "circle" as const,
          color: marker.color,
          text: marker.text,
          price: marker.price,
          size: 0.5,
        }))
    );
  }
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
export function StockChart({
  period,
  bars,
  compact = false,
  mainOverlayId = "sma",
  slotSec = 60,
  intradayChartBars,
  overlayCalcBars,
  fundStockBars,
  preClose,
  sessionDate,
  indexBars,
}: StockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const auctionBandRef = useRef<HTMLDivElement>(null);
  const auctionLineRef = useRef<HTMLDivElement>(null);
  const [hoverLabel, setHoverLabel] = useState<HoverPriceLabel | null>(null);
  const resolvedSlotSec = Math.max(1, Math.floor(slotSec));
  const continuousStartSlot = ashareContinuousStartSlot(resolvedSlotSec);
  const sessionLastSlot = ashareSessionLastSlot(resolvedSlotSec);
  const chartBars = useMemo(() => {
    if (period !== "intraday") {
      return toChartBars(bars, period);
    }
    if (intradayChartBars && intradayChartBars.length > 0) {
      return intradayChartBars;
    }
    return mapMinuteBarsToSlots(bars, resolvedSlotSec);
  }, [bars, period, intradayChartBars, resolvedSlotSec]);
  const showVolume =
    period === "intraday" || period === "day" || period === "week" || period === "month";
  const showMacd = period === "intraday" || period === "day";
  /** 分时 + MACD 时常驻资金趋势第四 pane */
  const withFundFlow = period === "intraday" && showMacd;
  const chartHeight = withFundFlow
    ? compact
      ? 460
      : 580
    : showMacd
      ? compact
        ? 400
        : 500
      : showVolume
        ? compact
          ? 340
          : 420
        : compact
          ? 292
          : 356;

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
        scaleMargins: withFundFlow
          ? { top: 0.04, bottom: 0.52 }
          : showMacd
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
            ? (time: Time) => formatIntradayCrosshairTime(time, resolvedSlotSec)
            : period === "day"
              ? (time: Time) => formatDailyCrosshairTime(time)
              : undefined,
      },
      timeScale: {
        borderColor: "#ffffff",
        timeVisible: period === "intraday",
        secondsVisible: false,
        tickMarkFormatter:
          period === "intraday"
            ? (time: Time) => formatIntradayTickMark(time, resolvedSlotSec)
            : undefined,
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

      // 先铺全天槽占位，保证关键时刻刻度落在轴上
      const placeholders = buildIntradaySlotPlaceholders(resolvedSlotSec);
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
        const avgByTime = new Map<number, number>();
        for (const point of avgPoints) {
          avgByTime.set(Number(remapMinuteChartTimeToSlot(point.time, resolvedSlotSec)), point.value);
        }
        avgSeries.setData(
          placeholders.map((point) => {
            const value = avgByTime.get(Number(point.time));
            return value == null ? point : { time: point.time, value };
          })
        );
      }

      // 预热线未到时先用当日 bars；sessionDate 须与 bars 实际日期一致（非交易日回退）
      const calcBars =
        overlayCalcBars && overlayCalcBars.length > 0 ? overlayCalcBars : bars;
      const built = buildMainOverlay(getMainOverlay(mainOverlayId), {
        chartBars,
        calcBars,
        preClose,
        sessionDate,
      });
      const hasOverlay =
        built.sticks.length > 0 ||
        built.markers.length > 0 ||
        built.lines.some((line) => line.points.length > 0);

      /**
       * 抄底叠加仍按分钟 ts 出点；槽宽≠60 时把坐标重映射到槽轴，避免与主图错位。
       * @param time 叠加原始时间
       */
      const mapOverlayTime = (time: Time): Time =>
        remapMinuteChartTimeToSlot(time, resolvedSlotSec);

      if (hasOverlay) {
        for (const color of INTRADAY_STICK_COLORS) {
          const sticks = built.sticks.filter((stick) => stick.color === color);
          if (sticks.length === 0) continue;
          const stickSeries = chart.addSeries(BarSeries, {
            upColor: color,
            downColor: color,
            thinBars: true,
            openVisible: false,
            lastValueVisible: false,
            priceLineVisible: false,
          });
          stickSeries.setData(
            sticks.map((stick) => ({
              time: mapOverlayTime(stick.time),
              open: stick.low,
              high: stick.high,
              low: stick.low,
              close: stick.high,
            }))
          );
        }

        for (const line of built.lines) {
          if (line.points.length === 0) continue;
          const overlaySeries = chart.addSeries(LineSeries, {
            color: line.color,
            lineWidth: line.lineWidth ?? 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          overlaySeries.setData(
            line.points.map((point) => ({
              time: mapOverlayTime(point.time),
              value: point.value,
            }))
          );
        }

        if (built.markers.length > 0) {
          createSeriesMarkers(
            series,
            [...built.markers]
              .sort((a, b) => Number(a.time) - Number(b.time))
              .map((marker) => ({
                time: mapOverlayTime(marker.time),
                position: "atPriceMiddle" as const,
                shape: "circle" as const,
                color: marker.color,
                text: marker.text,
                price: marker.price,
                size: 0.5,
              }))
          );
        }
      }

      if (showVolume) {
        addVolumePane(chart, chartBars, showMacd, withFundFlow);
      }
      if (showMacd) {
        addMacdPane(chart, chartBars, withFundFlow);
      }
      if (withFundFlow) {
        const stockForFund =
          fundStockBars && fundStockBars.length > 0
            ? fundStockBars
            : overlayCalcBars && overlayCalcBars.length > 0
              ? overlayCalcBars
              : bars;
        addFundFlowPane(chart, stockForFund, indexBars, sessionDate, resolvedSlotSec);
      }

      chart.timeScale().setVisibleRange({
        from: (INTRADAY_TIME_BASE + 0) as UTCTimestamp,
        to: (INTRADAY_TIME_BASE + sessionLastSlot) as UTCTimestamp,
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

      if (period === "day" || period === "week" || period === "month") {
        const overlay = getMainOverlay(mainOverlayId);
        for (const line of overlay.buildLines(chartBars)) {
          if (line.points.length === 0) continue;
          const maSeries = chart.addSeries(LineSeries, {
            color: line.color,
            lineWidth: line.lineWidth ?? 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          maSeries.setData(line.points);
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
        .timeToCoordinate((INTRADAY_TIME_BASE + continuousStartSlot) as Time);

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
  }, [
    bars,
    chartBars,
    chartHeight,
    continuousStartSlot,
    fundStockBars,
    indexBars,
    mainOverlayId,
    overlayCalcBars,
    period,
    preClose,
    resolvedSlotSec,
    sessionDate,
    sessionLastSlot,
    showMacd,
    showVolume,
    withFundFlow,
  ]);

  const heightClass = withFundFlow
    ? compact
      ? "h-[460px]"
      : "h-[580px]"
    : showMacd
      ? compact
        ? "h-[400px]"
        : "h-[500px]"
      : showVolume
        ? compact
          ? "h-[340px]"
          : "h-[420px]"
        : compact
          ? "h-[292px]"
          : "h-[356px]";

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
