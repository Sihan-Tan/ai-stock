/**
 * 主图叠加指标族注册表。
 */
import type { Time } from "lightweight-charts";
import {
  buildEmaSeries,
  buildSmaSeries,
  buildStdSeries,
  DAILY_MA_LINES,
  type ChartBar,
} from "./format";
import type { ChartPeriod } from "./types";

/** 一条主图叠加线。 */
export type MainOverlayLine = {
  label: string;
  color: string;
  /** lightweight-charts lineWidth，默认 1 */
  lineWidth?: 1 | 2 | 3 | 4;
  points: Array<{ time: Time; value: number }>;
};

/** 主图指标族。 */
export type MainOverlayDef = {
  id: string;
  label: string;
  periods: readonly ChartPeriod[];
  buildLines: (chartBars: ChartBar[]) => MainOverlayLine[];
};

/** 日/周/月可见。 */
const KLINE_PERIODS = ["day", "week", "month"] as const;

/**
 * 是否显示主图指标下拉。
 * @param period 当前周期
 */
export function shouldShowMainOverlaySelect(period: ChartPeriod): boolean {
  return (KLINE_PERIODS as readonly string[]).includes(period);
}

/**
 * 用现有 MA 配置生成叠加线。
 * @param chartBars 已转换的 K 线
 */
export function buildSmaOverlayLines(chartBars: ChartBar[]): MainOverlayLine[] {
  return DAILY_MA_LINES.map((ma) => ({
    label: ma.label,
    color: ma.color,
    points: buildSmaSeries(chartBars, ma.window),
  }));
}

/**
 * 按时间对齐两条同长度序列，逐点做二元运算。
 * @param left 左序列
 * @param right 右序列
 * @param op 运算
 */
function zipMapSeries(
  left: Array<{ time: Time; value: number }>,
  right: Array<{ time: Time; value: number }>,
  op: (a: number, b: number) => number
): Array<{ time: Time; value: number }> {
  const byTime = new Map(right.map((p) => [String(p.time), p.value]));
  const out: Array<{ time: Time; value: number }> = [];
  for (const p of left) {
    const b = byTime.get(String(p.time));
    if (b === undefined) continue;
    out.push({ time: p.time, value: op(p.value, b) });
  }
  return out;
}

/**
 * 通达信「均线战法」主图线（X_1=1）。
 *
 * 上轨/下轨 = MA60 ± 2*STD60；上上轨/下下轨 = MA90 ± 2*STD90；
 * 生命线 EMA144；红 EMA7；绿 EMA20。
 *
 * @param chartBars 已转换的 K 线
 */
export function buildMaTacticOverlayLines(chartBars: ChartBar[]): MainOverlayLine[] {
  const ma60 = buildSmaSeries(chartBars, 60);
  const std60 = buildStdSeries(chartBars, 60);
  const ma90 = buildSmaSeries(chartBars, 90);
  const std90 = buildStdSeries(chartBars, 90);

  return [
    {
      label: "上轨",
      color: "#22d3ee",
      points: zipMapSeries(ma60, std60, (m, s) => m + 2 * s),
    },
    {
      label: "上上轨",
      color: "#c080ff",
      points: zipMapSeries(ma90, std90, (m, s) => m + 2 * s),
    },
    {
      label: "生命线",
      color: "#22c55e",
      points: buildEmaSeries(chartBars, 144),
    },
    {
      label: "下下轨",
      color: "#c080ff",
      points: zipMapSeries(ma90, std90, (m, s) => m - 2 * s),
    },
    {
      label: "下轨",
      color: "#22d3ee",
      points: zipMapSeries(ma60, std60, (m, s) => m - 2 * s),
    },
    {
      label: "红",
      color: "#ef4444",
      lineWidth: 3,
      points: buildEmaSeries(chartBars, 7),
    },
    {
      label: "绿",
      color: "#22c55e",
      lineWidth: 2,
      points: buildEmaSeries(chartBars, 20),
    },
  ];
}

/** 全部主图族。 */
export const MAIN_OVERLAYS: readonly MainOverlayDef[] = [
  {
    id: "sma",
    label: "移动均线",
    periods: KLINE_PERIODS,
    buildLines: buildSmaOverlayLines,
  },
  {
    id: "ma_tactic",
    label: "均线战法",
    periods: KLINE_PERIODS,
    buildLines: buildMaTacticOverlayLines,
  },
] as const;

/**
 * 某周期可选的主图族。
 * @param period 当前周期
 */
export function listOverlaysForPeriod(period: ChartPeriod): MainOverlayDef[] {
  return MAIN_OVERLAYS.filter((o) => o.periods.includes(period));
}

/**
 * 按 id 取定义；找不到则回退 sma。
 * @param id 族 id
 */
export function getMainOverlay(id: string): MainOverlayDef {
  return MAIN_OVERLAYS.find((o) => o.id === id) ?? MAIN_OVERLAYS[0];
}
