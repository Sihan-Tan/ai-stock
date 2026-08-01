/**
 * 主图叠加指标族注册表（首版仅移动均线）。
 */
import type { Time } from "lightweight-charts";
import { buildSmaSeries, DAILY_MA_LINES, type ChartBar } from "./format";
import type { ChartPeriod } from "./types";

/** 一条主图叠加线。 */
export type MainOverlayLine = {
  label: string;
  color: string;
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

/** 全部主图族（首版仅 sma）。 */
export const MAIN_OVERLAYS: readonly MainOverlayDef[] = [
  {
    id: "sma",
    label: "移动均线",
    periods: KLINE_PERIODS,
    buildLines: buildSmaOverlayLines,
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
