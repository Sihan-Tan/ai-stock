/**
 * A 股涨跌 / 盈亏着色：涨红跌绿（正红负绿）。
 *
 * @param value 涨跌幅、盈亏等有符号数值；null/NaN 为中性灰
 */
export function chgToneClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "text-[var(--desk-mist)]";
  if (value > 0) return "text-[var(--danger)]";
  if (value < 0) return "text-[var(--success)]";
  return "text-[var(--desk-mist)]";
}
