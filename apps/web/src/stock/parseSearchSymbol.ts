/** 将用户输入规范为路由 symbol；非法返回 null */
export function parseSearchSymbol(raw: string): string | null {
  const s = raw.trim().toUpperCase();
  if (!s) return null;
  if (/^\d{6}$/.test(s)) {
    const head = s[0];
    const suffix = head === "5" || head === "6" || head === "9" ? "SH" : "SZ";
    return `${s}.${suffix}`;
  }
  if (/^\d{6}\.(SH|SZ)$/.test(s)) return s;
  return null;
}
