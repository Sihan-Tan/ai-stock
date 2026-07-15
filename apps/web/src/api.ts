/**
 * 调用后端 JSON API。
 * @param path API 路径
 * @param init fetch 选项
 */
export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as T;
}

/**
 * 将 API 时间（UTC）格式化为北京时间展示。
 * @param value ISO 时间字符串；无时区时按 UTC 解析
 */
export function formatBeijingTime(value: string | null | undefined): string {
  if (!value) return "—";
  const normalized =
    value.includes("T") && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? `${value}Z` : value;
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
