/**
 * A 股涨跌停幅度（小数，如 0.1=10%）。
 * @param symbol 标的代码
 * @param name 名称（用于识别 ST）
 */
export function limitRatio(symbol: string, name = ""): number {
  const sym = symbol.trim().toUpperCase();
  const code = sym.split(".")[0] ?? sym;
  const upperName = name.toUpperCase();
  if (upperName.includes("ST")) return 0.05;
  if (code.startsWith("300") || code.startsWith("301")) return 0.2;
  if (code.startsWith("688") || code.startsWith("689")) return 0.2;
  if (code.startsWith("8") || code.startsWith("4")) return 0.3;
  return 0.1;
}

/**
 * 按 A 股常见规则四舍五入到分。
 * @param value 价格
 */
export function roundPrice2(value: number): number {
  return Math.round(value * 100 + Number.EPSILON) / 100;
}

export type LimitTag = "up" | "down" | null;

/**
 * 判断是否触及涨停/跌停。
 * @param symbol 代码
 * @param last 最新价
 * @param preClose 昨收
 * @param name 名称
 */
export function detectLimitTag(
  symbol: string,
  last: number | null | undefined,
  preClose: number | null | undefined,
  name = ""
): LimitTag {
  if (last == null || preClose == null || preClose <= 0 || !Number.isFinite(last)) {
    return null;
  }
  const ratio = limitRatio(symbol, name);
  const up = roundPrice2(preClose * (1 + ratio));
  const down = roundPrice2(preClose * (1 - ratio));
  if (last >= up - 0.001) return "up";
  if (last <= down + 0.001) return "down";
  return null;
}

/**
 * 由最新价与昨收计算涨跌幅（%）。
 * @param last 最新价
 * @param preClose 昨收
 */
export function calcPctChg(
  last: number | null | undefined,
  preClose: number | null | undefined
): number | null {
  if (last == null || preClose == null || preClose === 0) return null;
  if (!Number.isFinite(last) || !Number.isFinite(preClose)) return null;
  return ((last - preClose) / preClose) * 100;
}
