import type { ChartPeriod } from "./types";

export type FactorPoint = { date: string; v: number | null };

export type GoldenPitOutputs = {
  gp_line: FactorPoint[];
  gp_pit: FactorPoint[];
  gp_blowoff: FactorPoint[];
};

/**
 * 是否在该周期加载黄金坑套件副图数据。
 * @param period 图表周期
 */
export function shouldLoadGoldenPit(period: ChartPeriod): boolean {
  return period === "day";
}

/**
 * 从 factors/series 响应取出 GOLDEN_PIT 输出；缺失则空数组。
 * @param payload API JSON
 */
export function pickGoldenPitOutputs(payload: unknown): GoldenPitOutputs {
  const empty: GoldenPitOutputs = { gp_line: [], gp_pit: [], gp_blowoff: [] };
  if (!payload || typeof payload !== "object") return empty;
  const series = (
    payload as { series?: Record<string, { outputs?: Record<string, FactorPoint[]> }> }
  ).series;
  const outs = series?.GOLDEN_PIT?.outputs;
  if (!outs) return empty;
  return {
    gp_line: outs.gp_line ?? [],
    gp_pit: outs.gp_pit ?? [],
    gp_blowoff: outs.gp_blowoff ?? [],
  };
}
