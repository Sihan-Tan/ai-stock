import { describe, expect, it } from "vitest";
import {
  applyPreset,
  boundsForPreset,
  defaultDateRangeValue,
  validateDateRange,
} from "./dateRange";

describe("dateRange helpers", () => {
  it("boundsForPreset 近1个月 / 近3个月 / 近半年 / 近1年", () => {
    expect(boundsForPreset("1m", "2026-07-21")).toEqual({
      start: "2026-06-21",
      end: "2026-07-21",
    });
    expect(boundsForPreset("3m", "2026-07-21")).toEqual({
      start: "2026-04-21",
      end: "2026-07-21",
    });
    expect(boundsForPreset("6m", "2026-07-21")).toEqual({
      start: "2026-01-21",
      end: "2026-07-21",
    });
    expect(boundsForPreset("1y", "2026-07-21")).toEqual({
      start: "2025-07-21",
      end: "2026-07-21",
    });
  });

  it("defaultDateRangeValue 默认为近1年", () => {
    const v = defaultDateRangeValue("2026-07-21");
    expect(v.preset).toBe("1y");
    expect(v.start).toBe("2025-07-21");
    expect(v.end).toBe("2026-07-21");
  });

  it("applyPreset 切到自定义保留原日期", () => {
    const next = applyPreset(
      { preset: "3m", start: "2026-04-21", end: "2026-07-21" },
      "custom",
      "2026-07-21"
    );
    expect(next).toEqual({
      preset: "custom",
      start: "2026-04-21",
      end: "2026-07-21",
    });
  });

  it("applyPreset 切到快捷项重算起止", () => {
    const next = applyPreset(
      { preset: "custom", start: "2020-01-01", end: "2020-06-01" },
      "1m",
      "2026-07-21"
    );
    expect(next.preset).toBe("1m");
    expect(next.start).toBe("2026-06-21");
    expect(next.end).toBe("2026-07-21");
  });

  it("validateDateRange 校验起止顺序", () => {
    expect(validateDateRange("2026-07-01", "2026-07-21")).toBeNull();
    expect(validateDateRange("2026-07-21", "2026-07-01")).toMatch(/不能晚于/);
    expect(validateDateRange("bad", "2026-07-01")).toMatch(/有效日期/);
  });
});
