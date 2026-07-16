import { describe, it, expect, beforeEach } from "vitest";
import {
  THEME_STORAGE_KEY,
  defaultTheme,
  parseTheme,
  applyTheme,
  readStoredTheme,
  type ThemeId,
} from "./theme";

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("parseTheme accepts desk-dark and desk-light only", () => {
    expect(parseTheme("desk-dark")).toBe("desk-dark");
    expect(parseTheme("desk-light")).toBe("desk-light");
    expect(parseTheme("nope")).toBe(defaultTheme);
    expect(parseTheme(null)).toBe(defaultTheme);
  });

  it("applyTheme sets data-theme and localStorage", () => {
    applyTheme("desk-light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("desk-light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("desk-light");
  });

  it("readStoredTheme falls back to default", () => {
    expect(readStoredTheme()).toBe(defaultTheme);
    localStorage.setItem(THEME_STORAGE_KEY, "desk-light");
    expect(readStoredTheme()).toBe("desk-light");
  });
});
