export type FactorPlot = "overlay" | "panel";

export type FactorMeta = {
  name: string;
  label: string;
  category: string;
  params: Record<string, unknown>;
  outputs: string[];
  plot: FactorPlot;
  default_enabled: boolean;
  enabled: boolean;
  /** 对应 TA-Lib 函数名 */
  talib?: string;
};

export type FactorPoint = { date: string; v: number | null };

export type FactorSeriesResponse = {
  symbol: string;
  engine: "talib" | "python";
  bars: { date: string; o: number; h: number; l: number; c: number; v: number }[];
  series: Record<string, { outputs: Record<string, FactorPoint[]> }>;
};
