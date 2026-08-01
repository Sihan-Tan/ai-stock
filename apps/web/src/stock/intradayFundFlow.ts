/**
 * 分时「资金趋势」副图：通达信公式（T=1）纯函数计算。
 */
import type { Time, UTCTimestamp } from "lightweight-charts";
import { getBeijingHourMinute, getBeijingHMS, toIntradayChartTime } from "./format";
import { INTRADAY_TIME_BASE, toAshareSessionSlot } from "./intradaySlots";
import { beijingDateFromTs } from "./overlayMath";
import { filterSignal, hhv, llv, refAt, smaTdx } from "./tdxMath";
import type { OhlcvBar } from "./types";

/** 配色（通达信近似）。 */
const COLOR = {
  mainIn: "#FF00FF",
  mainOut: "#0000FF",
  indexIn: "#EF4444",
  indexOut: "#22C55E",
  trend: "#F8FAFC",
  prepare: "#CC9900",
  buyStick: "#0099FF",
  buyText: "#FFFF00",
  sellCritical: "#FFFF00",
  escape: "#FFFF00",
  condIndexIn: "#EF4444",
  condIndexOut: "#22C55E",
  condMainIn: "#FF00FF",
  condMainOut: "#0000FF",
} as const;

export type FundFlowHist = {
  time: Time;
  value: number;
  color: string;
};

export type FundFlowStick = {
  time: Time;
  low: number;
  high: number;
  color: string;
};

export type FundFlowMarker = {
  time: Time;
  price: number;
  text: string;
  color: string;
};

export type FundFlowBuildResult = {
  /** 主力进/撤、大盘进/撤 等柱 */
  hists: FundFlowHist[];
  lines: Array<{
    label: string;
    color: string;
    points: Array<{ time: Time; value: number }>;
  }>;
  sticks: FundFlowStick[];
  markers: FundFlowMarker[];
};

export type FundFlowBuildInput = {
  /** 含预热的个股分钟线 */
  stockBars: OhlcvBar[];
  /** 含预热的指数分钟线（可空） */
  indexBars: OhlcvBar[];
  /** 当天 YYYY-MM-DD */
  sessionDate: string;
  /** 槽宽（秒）；传入时当日上图时间按槽轴对齐 */
  slotSec?: number;
};

/**
 * 将 bar ts 映射为分时图时间（分钟轴或槽轴）。
 * @param ts ISO 时间
 * @param slotSec 可选槽宽
 */
function toFundFlowChartTime(ts: string | undefined, slotSec?: number): UTCTimestamp | null {
  if (!ts) return null;
  if (slotSec == null) {
    return toIntradayChartTime(ts);
  }
  const ms = Date.parse(ts);
  if (Number.isNaN(ms)) return null;
  const { hour, minute, second } = getBeijingHMS(new Date(ms));
  const slot = toAshareSessionSlot(hour, minute, second, slotSec);
  if (slot == null) return null;
  return (INTRADAY_TIME_BASE + slot) as UTCTimestamp;
}

/**
 * 对数值序列做 EMA，α=2/(n+1)，与 buildEmaSeries 一致。
 * @param values 输入序列
 * @param n 周期
 */
export function emaValues(values: number[], n: number): number[] {
  if (values.length === 0 || n <= 0) return [];
  const alpha = 2 / (n + 1);
  const out: number[] = [];
  let ema = values[0]!;
  out.push(ema);
  for (let i = 1; i < values.length; i += 1) {
    ema = alpha * values[i]! + (1 - alpha) * ema;
    out.push(ema);
  }
  return out;
}

/**
 * 北京日历日 + HH:mm 对齐键（含预热日）。
 * @param ts ISO 时间
 */
function beijingMinuteKey(ts: string): string | null {
  const day = beijingDateFromTs(ts);
  const hm = getBeijingHourMinute(ts);
  if (!day || !hm) return null;
  return `${day}T${String(hm.hour).padStart(2, "0")}:${String(hm.minute).padStart(2, "0")}`;
}

/**
 * 过滤并排序有效分钟线。
 * @param bars 原始 bars
 */
function sortBarsWithTs(bars: OhlcvBar[]): OhlcvBar[] {
  return bars
    .filter((b) => b.ts != null && !Number.isNaN(Date.parse(b.ts)))
    .slice()
    .sort((a, b) => Date.parse(a.ts!) - Date.parse(b.ts!));
}

/**
 * 在指数序列上计算 VB（大盘资金分量）。
 * @param indexBars 已排序指数分钟线
 * @returns minuteKey → VB
 */
function computeIndexVbByKey(indexBars: OhlcvBar[]): Map<string, number> {
  const map = new Map<string, number>();
  if (indexBars.length === 0) return map;

  const v8 = indexBars.map(
    (b) => ((b.close * 2 + b.high + b.low) / 4),
  );
  const ema13 = emaValues(v8, 13);
  const ema34 = emaValues(v8, 34);
  const v9 = ema13.map((v, i) => v - ema34[i]!);
  const va = emaValues(v9, 3);
  const vb = v9.map((v, i) => (v - va[i]!) / 2);

  for (let i = 0; i < indexBars.length; i += 1) {
    const key = beijingMinuteKey(indexBars[i]!.ts!);
    if (key) map.set(key, vb[i]!);
  }
  return map;
}

/**
 * 构建分时「资金趋势」副图数据（T=1）。
 * @param input 个股/指数分钟与会话日
 */
export function buildIntradayFundFlow(
  input: FundFlowBuildInput,
): FundFlowBuildResult {
  const stockBars = sortBarsWithTs(input.stockBars);
  const indexBars = sortBarsWithTs(input.indexBars);
  const { sessionDate } = input;

  const empty: FundFlowBuildResult = {
    hists: [],
    lines: [{ label: "趋势线", color: COLOR.trend, points: [] }],
    sticks: [],
    markers: [],
  };
  if (stockBars.length === 0) return empty;

  const indexVbByKey = computeIndexVbByKey(indexBars);

  const closes = stockBars.map((b) => b.close);
  const highs = stockBars.map((b) => b.high);
  const lows = stockBars.map((b) => b.low);

  const v1 = stockBars.map(
    (b) => ((b.close * 2 + b.high + b.low) / 4) * 10,
  );
  const emaV1_13 = emaValues(v1, 13);
  const emaV1_34 = emaValues(v1, 34);
  const v2 = emaV1_13.map((v, i) => v - emaV1_34[i]!);
  const v3 = emaValues(v2, 5);
  const v4 = v2.map((v, i) => 2 * (v - v3[i]!) * 5.5);
  const mainIn = v4.map((v) => (v >= 0 ? v : 0));
  const mainOut = v4.map((v) => (v <= 0 ? v : 0));

  const llv55 = llv(lows, 55);
  const hhv55 = hhv(highs, 55);
  const rsv = closes.map((c, i) => {
    const range = hhv55[i]! - llv55[i]!;
    if (range === 0) return 0;
    return ((c - llv55[i]!) / range) * 100;
  });
  const sma5 = smaTdx(rsv, 5);
  const sma3 = smaTdx(sma5, 3);
  const v11 = sma5.map((v, i) => 3 * v - 2 * sma3[i]!);
  const trend = emaValues(v11, 3);
  const v12 = trend.map((t, i) => {
    const prev = refAt(trend, i, 1);
    if (prev == null || prev === 0) return Number.NaN;
    return ((t - prev) / prev) * 100;
  });

  const prepareStickCond = trend.map((t) => t <= 13);
  const prepareMark = filterSignal(prepareStickCond, 15);

  const buyStickCond = trend.map(
    (t, i) => t <= 13 && Number.isFinite(v12[i]!) && v12[i]! > 13,
  );
  const buyMark = filterSignal(buyStickCond, 10);

  const sellCriticalCond = trend.map((t, i) => {
    const prev = refAt(trend, i, 1);
    return prev != null && t > 90 && t > prev;
  });

  const escapeCond = trend.map((t, i) => {
    const prevT = refAt(trend, i, 1);
    const prevMain = refAt(mainIn, i, 1);
    return (
      prevT != null &&
      prevMain != null &&
      t > 90 &&
      t < prevT &&
      mainIn[i]! < prevMain
    );
  });
  const escapeMark = filterSignal(escapeCond, 8);

  const hists: FundFlowHist[] = [];
  const sticks: FundFlowStick[] = [];
  const markers: FundFlowMarker[] = [];
  const trendPoints: Array<{ time: Time; value: number }> = [];

  for (let i = 0; i < stockBars.length; i += 1) {
    const bar = stockBars[i]!;
    const day = beijingDateFromTs(bar.ts!);
    if (day !== sessionDate) continue;
    const time = toFundFlowChartTime(bar.ts, input.slotSec);
    if (time == null) continue;

    const t = trend[i]!;
    trendPoints.push({ time, value: t });

    const mi = mainIn[i]!;
    const mo = mainOut[i]!;
    if (mi > 0) {
      hists.push({ time, value: mi, color: COLOR.mainIn });
    } else if (mo < 0) {
      hists.push({ time, value: mo, color: COLOR.mainOut });
    } else {
      hists.push({ time, value: 0, color: COLOR.mainIn });
    }

    const key = beijingMinuteKey(bar.ts!);
    const vb = key != null ? indexVbByKey.get(key) : undefined;
    if (vb != null && Number.isFinite(vb)) {
      if (vb > 0) {
        hists.push({ time, value: vb, color: COLOR.indexIn });
      } else if (vb < 0) {
        hists.push({ time, value: vb, color: COLOR.indexOut });
      } else {
        hists.push({ time, value: 0, color: COLOR.indexIn });
      }
    }

    if (prepareStickCond[i]) {
      sticks.push({ time, low: 0, high: 8, color: COLOR.prepare });
    }
    if (prepareMark[i]) {
      markers.push({
        time,
        price: 20,
        text: "准备",
        color: COLOR.prepare,
      });
    }

    if (buyStickCond[i]) {
      sticks.push({ time, low: 0, high: 16, color: COLOR.buyStick });
    }
    if (buyMark[i]) {
      markers.push({
        time,
        price: 5,
        text: "买入",
        color: COLOR.buyText,
      });
    }

    if (sellCriticalCond[i]) {
      sticks.push({
        time,
        low: 95,
        high: 100,
        color: COLOR.sellCritical,
      });
    }

    if (escapeMark[i]) {
      markers.push({
        time,
        price: 90,
        text: "逃顶",
        color: COLOR.escape,
      });
    }

    // 条件加强柱：大盘/主力 × 趋势线阈值
    if (vb != null && Number.isFinite(vb)) {
      if (vb > 0 && t < 13) {
        sticks.push({ time, low: 0, high: 30, color: COLOR.condIndexIn });
      }
      if (vb < 0 && t > 90) {
        sticks.push({ time, low: 0, high: 30, color: COLOR.condIndexOut });
      }
    }
    if (mi > 0 && t < 13) {
      sticks.push({ time, low: 0, high: 40, color: COLOR.condMainIn });
    }
    if (mo < 0 && t > 90) {
      sticks.push({ time, low: 0, high: 40, color: COLOR.condMainOut });
    }
  }

  return {
    hists,
    lines: [{ label: "趋势线", color: COLOR.trend, points: trendPoints }],
    sticks,
    markers,
  };
}
