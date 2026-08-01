/**
 * 主图叠加用的交叉判定与交易日辅助。
 */
import type { OhlcvBar } from "./types";

/**
 * CROSS：A 上穿 B（前根 A≤B 且本根 A>B）。
 * @param a A 序列
 * @param b B 序列
 * @param i 当前下标
 */
export function crossUp(a: number[], b: number[], i: number): boolean {
  if (i < 1 || i >= a.length || i >= b.length) return false;
  return a[i - 1] <= b[i - 1] && a[i] > b[i];
}

/**
 * LONGCROSS：在 `i` 处，A 已上穿 B，且从交叉根起连续至少 `n` 根 A>B。
 * 通达信：`LONGCROSS(A,B,N)` 在满足「上穿后维持 N 根」的那根为真。
 * @param a A 序列
 * @param b B 序列
 * @param i 当前下标
 * @param n 维持根数
 */
export function longCrossUp(a: number[], b: number[], i: number, n: number): boolean {
  if (n < 1 || i < n || i >= a.length || i >= b.length) return false;
  const crossAt = i - n + 1;
  if (!crossUp(a, b, crossAt)) return false;
  for (let k = crossAt; k <= i; k += 1) {
    if (!(a[k] > b[k])) return false;
  }
  return true;
}

/**
 * 从 ISO ts 取北京日历日 YYYY-MM-DD。
 * @param ts ISO 时间
 */
export function beijingDateFromTs(ts: string): string | null {
  const ms = Date.parse(ts);
  if (Number.isNaN(ms)) return null;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(ms));
  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  if (!y || !m || !d) return null;
  return `${y}-${m}-${d}`;
}

/**
 * 过滤出北京日历日等于 `date` 的分钟线。
 * @param bars 分钟线
 * @param date YYYY-MM-DD
 */
export function filterBarsOnBeijingDate(bars: OhlcvBar[], date: string): OhlcvBar[] {
  return bars.filter((b) => b.ts != null && beijingDateFromTs(b.ts) === date);
}

/**
 * 从分钟线推断会话日（取最后一根有效 ts 的北京日历日）。
 * 非交易日接口可能回退到上一交易日数据，故不能用 beijingToday() 当 sessionDate。
 * @param bars 分钟线
 */
export function sessionDateFromBars(bars: OhlcvBar[]): string | undefined {
  for (let i = bars.length - 1; i >= 0; i -= 1) {
    const ts = bars[i]?.ts;
    if (!ts) continue;
    const day = beijingDateFromTs(ts);
    if (day) return day;
  }
  return undefined;
}

/**
 * 自 `date` 回推 `n` 个交易日（跳过周六日；不处理法定假日）。
 * @param date YYYY-MM-DD
 * @param n 交易日数
 */
export function shiftTradingDaysBack(date: string, n: number): string {
  const [ys, ms, ds] = date.split("-").map(Number);
  const cursor = new Date(Date.UTC(ys, ms - 1, ds));
  let left = n;
  while (left > 0) {
    cursor.setUTCDate(cursor.getUTCDate() - 1);
    const dow = cursor.getUTCDay(); // 0=Sun … 与日历日对齐（UTC 存的是日历分量）
    if (dow !== 0 && dow !== 6) left -= 1;
  }
  const y = cursor.getUTCFullYear();
  const m = String(cursor.getUTCMonth() + 1).padStart(2, "0");
  const d = String(cursor.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
