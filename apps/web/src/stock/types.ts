/** 仓位摘要（仅从监控持仓带入） */
export type PositionContext = {
  symbol: string;
  qty: number;
  cost: number;
  last?: number;
  pnl?: number;
  pnlPct?: number;
  weightPct?: number;
};

/** K 线展示周期。 */
export type ChartPeriod = "intraday" | "day" | "week" | "month";

/** 单根 OHLCV 行情数据。 */
export type OhlcvBar = {
  date?: string;
  ts?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
};
