/** 整段内容类型：纯 JSON 或按 Markdown 处理 */
export type ContentKind = "json" | "markdown";

/** 超过该字符数的 JSON 默认折叠（100KB） */
export const JSON_COLLAPSE_THRESHOLD = 100_000;

/**
 * 检测助手消息内容类型。
 * @param text 原始文本
 */
export function detectContentKind(text: string): ContentKind {
  const trimmed = text.trim();
  if (!trimmed) return "markdown";
  if (trimmed[0] !== "{" && trimmed[0] !== "[") return "markdown";
  try {
    JSON.parse(trimmed);
    return "json";
  } catch {
    return "markdown";
  }
}

/**
 * 美化 JSON 文本；解析失败则原样返回。
 * @param text 原始文本
 */
export function formatJsonText(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text.trim()), null, 2);
  } catch {
    return text;
  }
}

/**
 * 尝试解析 JSON；失败返回 null。
 * @param text 原始文本
 */
export function tryParseJson(text: string): unknown | null {
  try {
    return JSON.parse(text.trim());
  } catch {
    return null;
  }
}
