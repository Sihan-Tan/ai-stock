import { applyTheme, readStoredTheme } from "./theme";

/**
 * React 挂载前应用主题，减少闪烁。
 */
export function bootTheme(): void {
  applyTheme(readStoredTheme());
}
