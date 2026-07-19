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

/** 系统展示时区：北京时间 */
export const BEIJING_TZ = "Asia/Shanghai";

/**
 * 规范化 API 时间字符串以便解析。
 * 无时区的 ISO / ``YYYY-MM-DD HH:mm:ss`` 按 UTC 理解（与后端 utcnow 一致）。
 * @param value 原始时间串
 */
export function normalizeApiDateInput(value: string): string {
  const v = value.trim();
  if (!v) return v;
  if (/(?:Z|[+-]\d{2}:?\d{2})$/i.test(v)) return v;
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return `${v}T00:00:00Z`;
  const withT = v.includes("T") ? v : v.replace(" ", "T");
  return `${withT}Z`;
}

/**
 * 解析 API 时间为 Date；失败返回 null。
 * @param value ISO / 日期时间字符串
 */
export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(normalizeApiDateInput(value));
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * 将 API 时间格式化为北京时间完整展示。
 * @param value ISO 时间字符串；无时区时按 UTC 解析
 */
export function formatBeijingTime(value: string | null | undefined): string {
  const d = parseApiDate(value);
  if (!d) return value ? String(value) : "—";
  return d.toLocaleString("zh-CN", {
    timeZone: BEIJING_TZ,
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * 北京时间短格式（月-日 时:分:秒），用于列表密排。
 * @param value ISO 时间字符串
 */
export function formatBeijingTimeShort(value: string | null | undefined): string {
  const d = parseApiDate(value);
  if (!d) return value ? String(value) : "—";
  return d.toLocaleString("zh-CN", {
    timeZone: BEIJING_TZ,
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * 当前北京时间的时:分:秒。
 */
export function beijingNowClock(): string {
  return new Date().toLocaleTimeString("zh-CN", {
    timeZone: BEIJING_TZ,
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * 当前北京日期 ``YYYY-MM-DD``（用于表单默认日 / asof）。
 * @param date 基准时刻，默认现在
 */
export function beijingToday(date: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: BEIJING_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}
