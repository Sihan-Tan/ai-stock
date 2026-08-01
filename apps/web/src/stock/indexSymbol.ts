/**
 * 按标的市场解析通达信 INDEX 所用大盘指数代码。
 * @param stockSymbol 如 600519.SH
 * @returns 000001.SH / 399001.SZ；无法识别则 null
 */
export function resolveIndexSymbol(stockSymbol: string): string | null {
  const sym = stockSymbol.trim().toUpperCase();
  if (sym.endsWith(".SH")) return "000001.SH";
  if (sym.endsWith(".SZ")) return "399001.SZ";
  return null;
}
