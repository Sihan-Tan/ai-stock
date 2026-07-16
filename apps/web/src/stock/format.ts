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
