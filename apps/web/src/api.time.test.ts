import { describe, expect, it } from "vitest";
import {
  beijingToday,
  formatBeijingTime,
  formatBeijingTimeShort,
  normalizeApiDateInput,
  parseApiDate,
} from "./api";

describe("beijing time helpers", () => {
  it("normalizeApiDateInput 将无时区串视为 UTC", () => {
    expect(normalizeApiDateInput("2026-07-19T04:00:00")).toBe("2026-07-19T04:00:00Z");
    expect(normalizeApiDateInput("2026-07-19 04:00:00")).toBe("2026-07-19T04:00:00Z");
    expect(normalizeApiDateInput("2026-07-19")).toBe("2026-07-19T00:00:00Z");
    expect(normalizeApiDateInput("2026-07-19T04:00:00Z")).toBe("2026-07-19T04:00:00Z");
  });

  it("formatBeijingTime 将 UTC 转为北京时间", () => {
    // 04:00 UTC = 12:00 CST
    const text = formatBeijingTime("2026-07-19T04:00:00");
    expect(text).toContain("12:00:00");
    expect(text).toMatch(/2026/);
  });

  it("formatBeijingTimeShort 含月日与时分秒", () => {
    const text = formatBeijingTimeShort("2026-01-02T16:05:06Z");
    // 16:05 UTC = 次日 00:05 CST
    expect(text).toContain("00:05:06");
  });

  it("parseApiDate 失败返回 null", () => {
    expect(parseApiDate("not-a-date")).toBeNull();
    expect(parseApiDate(null)).toBeNull();
  });

  it("beijingToday 为 YYYY-MM-DD", () => {
    expect(beijingToday(new Date("2026-07-19T16:00:00Z"))).toBe("2026-07-20");
  });
});
