/**
 * 主图叠加指标族注册表。
 */
import type { Time, UTCTimestamp } from "lightweight-charts";
import {
  buildEmaSeries,
  buildSmaSeries,
  buildStdSeries,
  DAILY_MA_LINES,
  toIntradayChartTime,
  type ChartBar,
} from "./format";
import { beijingDateFromTs, crossUp, longCrossUp } from "./overlayMath";
import type { ChartPeriod, OhlcvBar } from "./types";

/** 一条主图叠加线。 */
export type MainOverlayLine = {
  label: string;
  color: string;
  /** lightweight-charts lineWidth，默认 1 */
  lineWidth?: 1 | 2 | 3 | 4;
  points: Array<{ time: Time; value: number }>;
};

/** STICKLINE 竖条（low→high）。 */
export type MainOverlayStick = {
  time: Time;
  low: number;
  high: number;
  color: string;
};

/** 信号文字标记。 */
export type MainOverlayMarker = {
  time: Time;
  price: number;
  text: string;
  color: string;
};

/** 一族完整叠加产出。 */
export type MainOverlayBuildResult = {
  lines: MainOverlayLine[];
  sticks: MainOverlayStick[];
  markers: MainOverlayMarker[];
};

/** 构建上下文。 */
export type MainOverlayBuildContext = {
  /** 当天会话轴 ChartBar（图上已有） */
  chartBars: ChartBar[];
  /** 含预热的原始分钟线（按 ts）；分时指标用 */
  calcBars?: OhlcvBar[];
  /** 昨收 */
  preClose?: number | null;
  /** 当天 YYYY-MM-DD（北京） */
  sessionDate?: string;
};

/** 主图指标族。 */
export type MainOverlayDef = {
  id: string;
  label: string;
  periods: readonly ChartPeriod[];
  /** 兼容旧调用：仅线 */
  buildLines: (chartBars: ChartBar[]) => MainOverlayLine[];
  /** 完整产出；缺省则包一层 buildLines */
  build?: (ctx: MainOverlayBuildContext) => MainOverlayBuildResult;
};

/** 日/周/月可见。 */
const KLINE_PERIODS = ["day", "week", "month"] as const;

/** 分时抄底配色（通达信色近似）。 */
const DIP = {
  ma30: "#60a5fa",
  strength: "#a78bfa",
  bandUp: "#0000FF",
  bandDown: "#00FF00",
  level: "#00DD00",
  signalStick: "#EAB308",
  starB: "#EAB308",
  star: "#EF4444",
} as const;

/**
 * 是否展示强弱色带 STICKLINE（MA30↔强弱）。
 * 暂时关闭以免遮挡分时；改 `true` 即可恢复，勿删下方生成逻辑。
 */
export const INTRADAY_DIP_SHOW_STRENGTH_BANDS = false;

/**
 * 是否显示主图指标下拉。
 * @param period 当前周期
 */
export function shouldShowMainOverlaySelect(period: ChartPeriod): boolean {
  return (
    (KLINE_PERIODS as readonly string[]).includes(period) || period === "intraday"
  );
}

/**
 * 统一调用 build / buildLines。
 * @param def 族定义
 * @param ctx 上下文
 */
export function buildMainOverlay(
  def: MainOverlayDef,
  ctx: MainOverlayBuildContext
): MainOverlayBuildResult {
  if (def.build) return def.build(ctx);
  return { lines: def.buildLines(ctx.chartBars), sticks: [], markers: [] };
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

/**
 * 将多日分钟线转为临时 ChartBar（唯一顺序时间），供 EMA 预热计算。
 * 禁止对多日 calcBars 使用 toChartBars(..., "intraday")，会话轴会撞车。
 * @param bars 含 ts 的分钟线
 */
function toSequentialCalcChartBars(bars: OhlcvBar[]): ChartBar[] {
  return bars.map((bar, i) => ({
    time: (i + 1) as UTCTimestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    value: bar.close,
    volume: Number(bar.volume ?? 0),
  }));
}

/**
 * 通达信「分时抄底」：EMA30/强弱色带、支撑阻力、交叉信号。
 * 不产出「现价」线（沿用分时面积线）。
 *
 * 非空产出依赖 {@link MainOverlayBuildContext.calcBars} 与
 * {@link MainOverlayBuildContext.sessionDate}（及可选 preClose）；仅传 chartBars 时返回空。
 * 调用方应通过 {@link buildMainOverlay} 传入完整上下文，勿单独依赖族上的 buildLines。
 *
 * @param ctx 构建上下文
 */
export function buildIntradayDipOverlay(
  ctx: MainOverlayBuildContext
): MainOverlayBuildResult {
  const sessionDate = ctx.sessionDate;
  const calcBars = ctx.calcBars ?? [];
  if (!sessionDate || calcBars.length === 0) {
    return { lines: [], sticks: [], markers: [] };
  }

  const sorted = [...calcBars]
    .filter((b) => b.ts != null)
    .sort((a, b) => Date.parse(a.ts!) - Date.parse(b.ts!));

  if (sorted.length === 0) {
    return { lines: [], sticks: [], markers: [] };
  }

  const tempBars = toSequentialCalcChartBars(sorted);
  const ema30All = buildEmaSeries(tempBars, 30);
  const ema900All = buildEmaSeries(tempBars, 900);

  const ma30Points: Array<{ time: Time; value: number }> = [];
  const strengthPoints: Array<{ time: Time; value: number }> = [];
  const resistPoints: Array<{ time: Time; value: number }> = [];
  const supportPoints: Array<{ time: Time; value: number }> = [];
  const sticks: MainOverlayStick[] = [];
  const markers: MainOverlayMarker[] = [];

  const closes: number[] = [];
  const supports: number[] = [];
  const resists: number[] = [];
  const times: Time[] = [];

  let runHigh = ctx.preClose ?? Number.NEGATIVE_INFINITY;
  let runLow = ctx.preClose ?? Number.POSITIVE_INFINITY;

  for (let i = 0; i < sorted.length; i += 1) {
    const bar = sorted[i];
    if (beijingDateFromTs(bar.ts!) !== sessionDate) continue;

    const time = toIntradayChartTime(bar.ts);
    if (time == null) continue;

    runHigh = Math.max(runHigh, bar.high);
    runLow = Math.min(runLow, bar.low);
    const p1 = runHigh - runLow;
    const resistance = runLow + (p1 * 7) / 8;
    const support = runLow + (p1 * 0.5) / 8;

    const ma30 = ema30All[i]!.value;
    const strength = ema900All[i]!.value;

    ma30Points.push({ time, value: ma30 });
    strengthPoints.push({ time, value: strength });
    resistPoints.push({ time, value: resistance });
    supportPoints.push({ time, value: support });

    if (INTRADAY_DIP_SHOW_STRENGTH_BANDS) {
      sticks.push({
        time,
        low: Math.min(ma30, strength),
        high: Math.max(ma30, strength),
        color: ma30 > strength ? DIP.bandUp : DIP.bandDown,
      });
    }

    closes.push(bar.close);
    supports.push(support);
    resists.push(resistance);
    times.push(time);
  }

  for (let j = 0; j < closes.length; j += 1) {
    if (crossUp(supports, closes, j)) {
      sticks.push({
        time: times[j]!,
        low: Math.min(supports[j]!, resists[j]!),
        high: Math.max(supports[j]!, resists[j]!),
        color: DIP.signalStick,
      });
    }
    if (longCrossUp(supports, closes, j, 2)) {
      markers.push({
        time: times[j]!,
        price: supports[j]! * 1.001,
        text: "★B",
        color: DIP.starB,
      });
    }
    if (longCrossUp(closes, resists, j, 2)) {
      markers.push({
        time: times[j]!,
        price: closes[j]!,
        text: "★",
        color: DIP.star,
      });
    }
  }

  return {
    lines: [
      { label: "MA30", color: DIP.ma30, points: ma30Points },
      { label: "强弱", color: DIP.strength, points: strengthPoints },
      { label: "阻力", color: DIP.level, points: resistPoints },
      { label: "支撑", color: DIP.level, points: supportPoints },
    ],
    sticks,
    markers,
  };
}

/** 空叠加（分时默认「无」）。 */
function buildEmptyOverlay(): MainOverlayBuildResult {
  return { lines: [], sticks: [], markers: [] };
}

/**
 * intraday_dip 的 buildLines 兼容签名；无 calcBars/sessionDate 时 lines 恒为空。
 * @param chartBars 当天会话轴（不足以单独计算分时抄底）
 */
function buildIntradayDipOverlayLines(chartBars: ChartBar[]): MainOverlayLine[] {
  return buildIntradayDipOverlay({ chartBars }).lines;
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
  {
    id: "none",
    label: "无",
    periods: ["intraday"],
    buildLines: () => [],
    build: () => buildEmptyOverlay(),
  },
  {
    id: "intraday_dip",
    label: "分时抄底",
    periods: ["intraday"],
    buildLines: buildIntradayDipOverlayLines,
    build: buildIntradayDipOverlay,
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
