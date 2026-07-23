import { describe, expect, it } from "vitest";
import { chgToneClass } from "./chgTone";

describe("chgToneClass", () => {
  it("正数为红（涨/盈）", () => {
    expect(chgToneClass(1)).toBe("text-[var(--danger)]");
    expect(chgToneClass(0.01)).toBe("text-[var(--danger)]");
  });

  it("负数为绿（跌/亏）", () => {
    expect(chgToneClass(-1)).toBe("text-[var(--success)]");
    expect(chgToneClass(-0.01)).toBe("text-[var(--success)]");
  });

  it("零与空值为中性灰", () => {
    expect(chgToneClass(0)).toBe("text-[var(--desk-mist)]");
    expect(chgToneClass(null)).toBe("text-[var(--desk-mist)]");
    expect(chgToneClass(undefined)).toBe("text-[var(--desk-mist)]");
    expect(chgToneClass(Number.NaN)).toBe("text-[var(--desk-mist)]");
  });
});
