import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

export type EquityPoint = {
  date?: string;
  value?: number;
};

export type TradeMarkerSource = {
  dt_open?: string;
  dt_close?: string;
};

type EquityCurveChartProps = {
  /** 权益点（含 date / value）；图中按相对首点换算为收益率 % */
  points: EquityPoint[];
  /** 成交明细，用于标注买卖点 */
  trades?: TradeMarkerSource[];
  /** 图表高度 */
  height?: number;
};

/**
 * 回测收益曲线（相对初始权益的累计收益率 %），并标注买卖点。
 * @param props 权益序列、成交与高度
 */
export function EquityCurveChart({
  points,
  trades = [],
  height = 320,
}: EquityCurveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    const seriesData = toReturnSeries(points);
    if (!container || seriesData.length === 0) {
      return;
    }

    const chart: IChartApi = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(232, 236, 244, 0.72)",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.06)" },
        horzLines: { color: "rgba(255, 255, 255, 0.06)" },
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.12)",
        scaleMargins: { top: 0.16, bottom: 0.1 },
      },
      localization: {
        priceFormatter: (price: number) => `${price.toFixed(2)}%`,
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.12)",
        timeVisible: seriesData.some((p) => typeof p.time === "number"),
        secondsVisible: false,
      },
      crosshair: {
        horzLine: { labelVisible: true },
        vertLine: { labelVisible: true },
      },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: "#d4a574",
      topColor: "rgba(212, 165, 116, 0.32)",
      bottomColor: "rgba(212, 165, 116, 0.02)",
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
      priceFormat: {
        type: "custom",
        formatter: (price: number) => `${price.toFixed(2)}%`,
        minMove: 0.01,
      },
    });
    series.setData(seriesData);

    const markers = buildTradeMarkers(trades, seriesData);
    if (markers.length) {
      createSeriesMarkers(series, markers);
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [points, trades, height]);

  if (!points.length) {
    return null;
  }

  return <div ref={containerRef} className="w-full" style={{ height }} />;
}

type ChartDatum = { time: Time; value: number };

/**
 * 权益 → 累计收益率（%），相对首个有效权益点。
 * @param points 原始权益点
 */
function toReturnSeries(points: EquityPoint[]): ChartDatum[] {
  const useIntraday = points.some((p) => isIntradayDate(p.date));
  const raw: ChartDatum[] = [];
  const seen = new Set<string>();

  for (const point of points) {
    if (point.value == null || !Number.isFinite(point.value) || !point.date) {
      continue;
    }
    const time = useIntraday ? toUtcTimestamp(point.date) : toBusinessDay(point.date);
    if (time == null) {
      continue;
    }
    const key = String(time);
    if (seen.has(key)) {
      const idx = raw.findIndex((row) => String(row.time) === key);
      if (idx >= 0) {
        raw[idx] = { time, value: point.value };
      }
      continue;
    }
    seen.add(key);
    raw.push({ time, value: point.value });
  }
  if (!raw.length) return [];
  const base = raw[0].value;
  if (!base) return raw.map((row) => ({ time: row.time, value: 0 }));
  return raw.map((row) => ({
    time: row.time,
    value: ((row.value / base) - 1) * 100,
  }));
}

/**
 * 由成交明细生成买卖点标记（A 股习惯：红买绿卖）。
 * @param trades 成交
 * @param seriesData 已对齐的收益序列（用于校验时间是否存在）
 */
function buildTradeMarkers(
  trades: TradeMarkerSource[],
  seriesData: ChartDatum[]
): SeriesMarker<Time>[] {
  const timeSet = new Set(seriesData.map((row) => String(row.time)));
  const useIntraday = seriesData.some((row) => typeof row.time === "number");
  const markers: SeriesMarker<Time>[] = [];

  for (const trade of trades) {
    const buyTime = resolveMarkerTime(trade.dt_open, useIntraday);
    if (buyTime != null && timeSet.has(String(buyTime))) {
      markers.push({
        time: buyTime,
        position: "belowBar",
        color: "#ef4444",
        shape: "arrowUp",
        text: "买",
      });
    }
    const sellTime = resolveMarkerTime(trade.dt_close, useIntraday);
    if (sellTime != null && timeSet.has(String(sellTime))) {
      markers.push({
        time: sellTime,
        position: "aboveBar",
        color: "#22c55e",
        shape: "arrowDown",
        text: "卖",
      });
    }
  }

  markers.sort((a, b) => {
    const ta = typeof a.time === "number" ? a.time : Date.parse(String(a.time));
    const tb = typeof b.time === "number" ? b.time : Date.parse(String(b.time));
    return ta - tb;
  });
  return markers;
}

/**
 * 将成交时间对齐到图表 time。
 * @param date 成交时间
 * @param useIntraday 是否分钟轴
 */
function resolveMarkerTime(date: string | undefined, useIntraday: boolean): Time | null {
  if (!date) return null;
  return useIntraday || isIntradayDate(date) ? toUtcTimestamp(date) : toBusinessDay(date);
}

/**
 * 是否含有效时分（非全日线 00:00:00）。
 * @param date 时间字符串
 */
function isIntradayDate(date?: string): boolean {
  if (!date) return false;
  const m = date.match(/(\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return false;
  return !(m[1] === "00" && m[2] === "00" && (m[3] ?? "00") === "00");
}

/**
 * 取业务日 YYYY-MM-DD。
 * @param date 时间字符串
 */
function toBusinessDay(date: string): Time | null {
  const m = date.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  return `${m[1]}-${m[2]}-${m[3]}` as Time;
}

/**
 * 本地墙钟时间按字面转 UTCTimestamp。
 * @param date 时间字符串
 */
function toUtcTimestamp(date: string): UTCTimestamp | null {
  const m = date.match(
    /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/
  );
  if (!m) {
    const day = toBusinessDay(date);
    if (!day || typeof day !== "string") return null;
    const [y, mo, d] = day.split("-").map(Number);
    return (Date.UTC(y, mo - 1, d) / 1000) as UTCTimestamp;
  }
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const hh = Number(m[4]);
  const mm = Number(m[5]);
  const ss = Number(m[6] ?? "0");
  return (Date.UTC(y, mo - 1, d, hh, mm, ss) / 1000) as UTCTimestamp;
}
