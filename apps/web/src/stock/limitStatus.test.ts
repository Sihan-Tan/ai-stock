import { describe, expect, it } from "vitest";
import { calcPctChg, detectLimitTag, limitRatio } from "./limitStatus";

describe("limitRatio", () => {
  it("uses 20% for ChiNext and STAR", () => {
    expect(limitRatio("300750.SZ")).toBe(0.2);
    expect(limitRatio("688981.SH")).toBe(0.2);
  });

  it("uses 5% for ST names", () => {
    expect(limitRatio("600001.SH", "ST示例")).toBe(0.05);
  });

  it("defaults to 10%", () => {
    expect(limitRatio("600519.SH", "贵州茅台")).toBe(0.1);
  });
});

describe("detectLimitTag", () => {
  it("detects limit up and down", () => {
    expect(detectLimitTag("600519.SH", 110, 100)).toBe("up");
    expect(detectLimitTag("600519.SH", 90, 100)).toBe("down");
    expect(detectLimitTag("600519.SH", 105, 100)).toBeNull();
  });
});

describe("calcPctChg", () => {
  it("computes percent change", () => {
    expect(calcPctChg(110, 100)).toBeCloseTo(10);
    expect(calcPctChg(null, 100)).toBeNull();
  });
});
