import type { UTCTimestamp } from "lightweight-charts";
import type { ChartBar } from "./format";
import {
  getBeijingHourMinute,
  sessionMinuteIndexToHourMinute,
  toAshareSessionIndex,
} from "./format";
import type { OhlcvBar } from "./types";

/** 用于图表的伪时间基数，避免与真实 unix 混淆。 */
export const INTRADAY_TIME_BASE = 1_000_000;

/** 会话最后一秒序号（15:00:00 = 分钟 index 255 × 60）。 */
const SESSION_LAST_SECOND = 255 * 60;

/**
 * 校验并钳制分时刷新间隔（秒）到 [5, 60]；非法回退 10。
 * @param raw 原始输入
 */
export function clampIntradayPollIntervalSec(raw: unknown): number {
  const n = Math.round(Number(raw));
  if (!Number.isFinite(n)) return 10;
  return Math.min(60, Math.max(5, n));
}

/**
 * 将北京时分秒映射为会话内秒序号（与 `toAshareSessionIndex` 同边界）。
 * 11:30 与 13:00 共分钟点时，秒序按共点 index * 60 + second。
 *
 * @param hour 时
 * @param minute 分
 * @param second 秒（0–59）
 */
function toAshareSessionSecond(hour: number, minute: number, second: number): number | null {
  const minuteIndex = toAshareSessionIndex(hour, minute);
  if (minuteIndex == null) return null;
  const sec = Number.isFinite(second) ? Math.min(59, Math.max(0, Math.floor(second))) : 0;
  return minuteIndex * 60 + sec;
}

/**
 * 将北京时分秒映射到槽序号（slotSec 为槽宽）。
 * @param hour 时
 * @param minute 分
 * @param second 秒
 * @param slotSec 槽宽（秒）
 * @returns null 若非交易时段
 */
export function toAshareSessionSlot(
  hour: number,
  minute: number,
  second: number,
  slotSec: number
): number | null {
  const sessionSecond = toAshareSessionSecond(hour, minute, second);
  if (sessionSecond == null) return null;
  const width = Math.max(1, Math.floor(slotSec));
  return Math.floor(sessionSecond / width);
}

/**
 * 全天槽最后下标（含），对应 15:00:00。
 * @param slotSec 槽宽（秒）
 */
export function ashareSessionLastSlot(slotSec: number): number {
  const width = Math.max(1, Math.floor(slotSec));
  return Math.floor(SESSION_LAST_SECOND / width);
}

/**
 * 连续竞价起点槽（09:30:00）。
 * @param slotSec 槽宽（秒）
 */
export function ashareContinuousStartSlot(slotSec: number): number {
  return toAshareSessionSlot(9, 30, 0, slotSec) as number;
}

/**
 * 生成分时全天槽占位时间点。
 * @param slotSec 槽宽（秒）
 */
export function buildIntradaySlotPlaceholders(slotSec: number): Array<{ time: UTCTimestamp }> {
  const last = ashareSessionLastSlot(slotSec);
  const points: Array<{ time: UTCTimestamp }> = [];
  for (let index = 0; index <= last; index += 1) {
    points.push({ time: (INTRADAY_TIME_BASE + index) as UTCTimestamp });
  }
  return points;
}

/**
 * 分钟 OHLCV → 槽序列 ChartBar（落到分钟起点槽；同槽后写覆盖）。
 * @param bars 分钟线
 * @param slotSec 槽宽（秒）
 */
export function mapMinuteBarsToSlots(bars: OhlcvBar[], slotSec: number): ChartBar[] {
  const sorted = [...bars].sort((a, b) => {
    const timeA = a.ts ? Date.parse(a.ts) : Number.NaN;
    const timeB = b.ts ? Date.parse(b.ts) : Number.NaN;
    return timeA - timeB;
  });

  const bySlot = new Map<number, ChartBar>();
  for (const bar of sorted) {
    if (!bar.ts) continue;
    const hm = getBeijingHourMinute(bar.ts);
    if (!hm) continue;
    // 分钟线落在该分钟起点所在槽（秒=0）
    const slotIndex = toAshareSessionSlot(hm.hour, hm.minute, 0, slotSec);
    if (slotIndex == null) continue;
    const time = (INTRADAY_TIME_BASE + slotIndex) as UTCTimestamp;
    bySlot.set(slotIndex, {
      time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      value: bar.close,
      volume: Number(bar.volume ?? 0),
    });
  }
  return [...bySlot.values()].sort((a, b) => Number(a.time) - Number(b.time));
}

/**
 * 在槽序列上写入/更新某一槽的 close/value（报价补点）。
 * @param slots 现有槽序列
 * @param slotIndex 槽序号
 * @param price 现价
 */
export function upsertSlotPrice(
  slots: ChartBar[],
  slotIndex: number,
  price: number
): ChartBar[] {
  const time = (INTRADAY_TIME_BASE + slotIndex) as UTCTimestamp;
  const next = [...slots];
  const idx = next.findIndex((bar) => Number(bar.time) === Number(time));
  if (idx >= 0) {
    const prev = next[idx];
    next[idx] = {
      ...prev,
      close: price,
      value: price,
      high: Math.max(prev.high, price),
      low: Math.min(prev.low, price),
    };
    return next;
  }
  next.push({
    time,
    open: price,
    high: price,
    low: price,
    close: price,
    value: price,
  });
  return next.sort((a, b) => Number(a.time) - Number(b.time));
}

/**
 * 将槽序列 ChartBar 转为伪 OHLCV（供资金趋势等按 ts 预热拼接）。
 * @param bars 槽轴 ChartBar
 * @param sessionDate 会话日 YYYY-MM-DD（北京）
 * @param slotSec 槽宽（秒）
 */
export function chartBarsToPseudoOhlcv(
  bars: ChartBar[],
  sessionDate: string,
  slotSec: number
): OhlcvBar[] {
  const width = Math.max(1, Math.floor(slotSec));
  return bars.map((bar) => {
    const slotIndex = Number(bar.time) - INTRADAY_TIME_BASE;
    const sessionSecond = slotIndex * width;
    const minuteIndex = Math.floor(sessionSecond / 60);
    const second = sessionSecond - minuteIndex * 60;
    const hm = sessionMinuteIndexToHourMinute(minuteIndex);
    const ts = `${sessionDate}T${String(hm.hour).padStart(2, "0")}:${String(hm.minute).padStart(2, "0")}:${String(second).padStart(2, "0")}+08:00`;
    return {
      ts,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: Number(bar.volume ?? 0),
    };
  });
}
