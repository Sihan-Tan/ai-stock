import type { Time, UTCTimestamp } from "lightweight-charts";
import type { ChartPeriod, OhlcvBar } from "./types";

export type ChartBar = {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  value: number;
};

/** 分时会话摘要（均价 / OHLC）。 */
export type IntradaySummary = {
  avg: number | null;
  open: number | null;
  close: number | null;
  high: number | null;
  low: number | null;
};

/**
 * 将接口 OHLCV 数据转换为 lightweight-charts 所需的时间序列格式。
 * @param bars 接口返回的原始行情数据
 * @param period 当前展示周期
 */
export function toChartBars(bars: OhlcvBar[], period: ChartPeriod): ChartBar[] {
  const sortedBars = [...bars].sort((a, b) => {
    if (period === "intraday") {
      const timeA = a.ts ? Date.parse(a.ts) : Number.NaN;
      const timeB = b.ts ? Date.parse(b.ts) : Number.NaN;
      return timeA - timeB;
    }

    return (a.date ?? "").localeCompare(b.date ?? "");
  });

  return sortedBars.flatMap((bar) => {
    const time = period === "intraday" ? toUnixSeconds(bar.ts) : toBusinessDay(bar.date);

    if (time == null) {
      return [];
    }

    return [
      {
        time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        value: bar.close,
      },
    ];
  });
}

/**
 * 估算单根分钟线的成交额（元）与成交量权重。
 *
 * xtdata 分钟成交量常为「手」：若 amount/volume 明显偏离本根价格，则按手×100 折算股数。
 *
 * @param bar 分钟 OHLCV
 */
function barTurnoverAndVolume(bar: OhlcvBar): { turnover: number; volume: number } {
  const volume = Number(bar.volume ?? 0);
  const amount = Number(bar.amount ?? 0);
  if (volume <= 0) {
    return { turnover: 0, volume: 0 };
  }
  if (amount > 0) {
    const raw = amount / volume;
    const hi = Math.max(bar.high, bar.close, bar.open);
    const lo = Math.min(bar.low, bar.close, bar.open);
    // amount/volume 远高于价位 → 成交量按「手」计
    if (raw > hi * 1.5 && raw > lo * 1.5) {
      return { turnover: amount, volume: volume * 100 };
    }
    return { turnover: amount, volume };
  }
  // 无成交额：用收盘价×量做权，手/股不影响均价量纲
  return { turnover: bar.close * volume, volume };
}

/**
 * 计算分时累计均价序列（日内 VWAP）。
 *
 * @param bars 分钟 OHLCV（无需预排序）
 */
export function buildIntradayAvgSeries(
  bars: OhlcvBar[]
): Array<{ time: UTCTimestamp; value: number }> {
  const sorted = [...bars].sort((a, b) => {
    const timeA = a.ts ? Date.parse(a.ts) : Number.NaN;
    const timeB = b.ts ? Date.parse(b.ts) : Number.NaN;
    return timeA - timeB;
  });

  let turnoverSum = 0;
  let volumeSum = 0;
  const points: Array<{ time: UTCTimestamp; value: number }> = [];

  for (const bar of sorted) {
    const time = toUnixSeconds(bar.ts);
    if (time == null) continue;
    const { turnover, volume } = barTurnoverAndVolume(bar);
    turnoverSum += turnover;
    volumeSum += volume;
    if (volumeSum > 0) {
      points.push({ time, value: turnoverSum / volumeSum });
    }
  }
  return points;
}

/**
 * 由分钟线汇总分时均价与开高低收。
 *
 * 均价为日内累计成交额/累计成交量（最新一点 VWAP）。
 *
 * @param bars 分钟 OHLCV
 */
export function summarizeIntradayBars(bars: OhlcvBar[]): IntradaySummary {
  if (!bars.length) {
    return { avg: null, open: null, close: null, high: null, low: null };
  }

  const sorted = [...bars].sort((a, b) => {
    const timeA = a.ts ? Date.parse(a.ts) : Number.NaN;
    const timeB = b.ts ? Date.parse(b.ts) : Number.NaN;
    return timeA - timeB;
  });

  let high = -Infinity;
  let low = Infinity;
  for (const bar of sorted) {
    high = Math.max(high, bar.high);
    low = Math.min(low, bar.low);
  }

  const avgSeries = buildIntradayAvgSeries(sorted);
  const avg =
    avgSeries.length > 0
      ? avgSeries[avgSeries.length - 1].value
      : sorted.reduce((sum, bar) => sum + bar.close, 0) / sorted.length;

  return {
    avg: Number.isFinite(avg) ? avg : null,
    open: sorted[0].open,
    close: sorted[sorted.length - 1].close,
    high: Number.isFinite(high) ? high : null,
    low: Number.isFinite(low) ? low : null,
  };
}

/**
 * 提取日线、周线、月线可用的 YYYY-MM-DD 交易日。
 * @param value 接口返回的日期
 */
function toBusinessDay(value: string | undefined): string | null {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

/**
 * 将 ISO 时间转换为 Unix 秒时间戳。
 * @param value 接口返回的分时数据时间
 */
function toUnixSeconds(value: string | undefined): UTCTimestamp | null {
  if (!value) {
    return null;
  }

  const milliseconds = Date.parse(value);
  return Number.isNaN(milliseconds) ? null : (Math.floor(milliseconds / 1000) as UTCTimestamp);
}
