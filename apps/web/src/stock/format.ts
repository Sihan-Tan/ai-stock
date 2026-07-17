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

/** 上午时段跨度（09:30→11:30 = 120 分钟）。 */
const AM_SPAN = 11 * 60 + 30 - (9 * 60 + 30);
/** 用于图表的伪时间基数，避免与真实 unix 混淆。 */
const INTRADAY_TIME_BASE = 1_000_000;

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
    const time =
      period === "intraday" ? toIntradayChartTime(bar.ts) : toBusinessDay(bar.date);

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
 * 读取北京时间的时、分。
 * @param value ISO 时间
 */
export function getBeijingHourMinute(value: string): { hour: number; minute: number } | null {
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return null;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(ms));
  const hour = Number(parts.find((p) => p.type === "hour")?.value);
  const minute = Number(parts.find((p) => p.type === "minute")?.value);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
  return { hour, minute };
}

/**
 * 将北京时间映射为连续交易分钟序号（跳过午休）。
 *
 * 09:30→0 … 11:30→120；13:00→121 … 15:00→241。
 *
 * @param hour 时
 * @param minute 分
 */
export function toAshareSessionIndex(hour: number, minute: number): number | null {
  const mins = hour * 60 + minute;
  const amStart = 9 * 60 + 30;
  const amEnd = 11 * 60 + 30;
  const pmStart = 13 * 60;
  const pmEnd = 15 * 60;

  if (mins >= amStart && mins <= amEnd) {
    return mins - amStart;
  }
  if (mins >= pmStart && mins <= pmEnd) {
    return AM_SPAN + 1 + (mins - pmStart);
  }
  return null;
}

/**
 * 将连续交易分钟序号格式化为 HH:mm。
 * @param sessionIndex 会话分钟序号
 */
export function formatAshareSessionLabel(sessionIndex: number): string {
  const idx = Math.round(sessionIndex);
  let mins: number;
  if (idx <= AM_SPAN) {
    mins = 9 * 60 + 30 + idx;
  } else {
    mins = 13 * 60 + (idx - AM_SPAN - 1);
  }
  const hour = Math.floor(mins / 60);
  const minute = mins % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

/**
 * 从图表伪时间还原会话序号。
 * @param chartTime lightweight-charts 时间
 */
export function chartTimeToSessionIndex(chartTime: Time): number {
  return Number(chartTime) - INTRADAY_TIME_BASE;
}

/**
 * 分时图时间轴格式化（北京交易时段）。
 * @param chartTime 图表时间
 */
export function formatIntradayTickMark(chartTime: Time): string {
  return formatAshareSessionLabel(chartTimeToSessionIndex(chartTime));
}

/**
 * 将分钟线时间转为分时图连续轴坐标；非交易时段返回 null。
 * @param value ISO 时间
 */
export function toIntradayChartTime(value: string | undefined): UTCTimestamp | null {
  if (!value) return null;
  const hm = getBeijingHourMinute(value);
  if (!hm) return null;
  const index = toAshareSessionIndex(hm.hour, hm.minute);
  if (index == null) return null;
  return (INTRADAY_TIME_BASE + index) as UTCTimestamp;
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
    const time = toIntradayChartTime(bar.ts);
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

/** 日 K 均线配置（周期与颜色）。 */
export const DAILY_MA_LINES = [
  { window: 5, color: "#fbbf24", label: "MA5" },
  { window: 10, color: "#38bdf8", label: "MA10" },
  { window: 20, color: "#c084fc", label: "MA20" },
  { window: 30, color: "#2dd4bf", label: "MA30" },
  { window: 60, color: "#fb923c", label: "MA60" },
] as const;

/**
 * 计算简单移动平均线序列。
 *
 * @param bars 已按时间排序的 K 线
 * @param window 均线窗口（交易日数）
 */
export function buildSmaSeries(
  bars: ChartBar[],
  window: number
): Array<{ time: Time; value: number }> {
  if (window <= 0 || bars.length < window) {
    return [];
  }

  const points: Array<{ time: Time; value: number }> = [];
  let sum = 0;

  for (let i = 0; i < bars.length; i += 1) {
    sum += bars[i].close;
    if (i >= window) {
      sum -= bars[i - window].close;
    }
    if (i >= window - 1) {
      points.push({ time: bars[i].time, value: sum / window });
    }
  }

  return points;
}

/**
 * 提取日线、周线、月线可用的 YYYY-MM-DD 交易日。
 * @param value 接口返回的日期
 */
function toBusinessDay(value: string | undefined): string | null {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}
