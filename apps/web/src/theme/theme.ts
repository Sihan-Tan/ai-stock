export type ThemeId = "desk-dark" | "desk-light";

export const THEME_STORAGE_KEY = "desk-theme";
export const defaultTheme: ThemeId = "desk-dark";

/**
 * 解析主题 id；非法值回退默认深色。
 * @param raw localStorage 或属性原始值
 */
export function parseTheme(raw: string | null | undefined): ThemeId {
  if (raw === "desk-dark" || raw === "desk-light") return raw;
  return defaultTheme;
}

/**
 * 读取已存主题。
 */
export function readStoredTheme(): ThemeId {
  try {
    return parseTheme(localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return defaultTheme;
  }
}

/**
 * 应用主题到 documentElement 并持久化。
 * @param theme 主题 id
 */
export function applyTheme(theme: ThemeId): void {
  const next = parseTheme(theme);
  const root = document.documentElement;
  root.setAttribute("data-theme", next);
  if (next === "desk-dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    /* ignore quota / private mode */
  }
}
