import { describe, expect, it } from "vitest";
import { resolveSearchNavigation } from "./resolveSearchNavigation";

describe("resolveSearchNavigation", () => {
  it("prefers direct code parse", () => {
    expect(
      resolveSearchNavigation("600519", [{ symbol: "000001.SZ", name: "平安银行" }])
    ).toBe("600519.SH");
  });

  it("falls back to first candidate", () => {
    expect(
      resolveSearchNavigation("贵州", [
        { symbol: "600519.SH", name: "贵州茅台" },
        { symbol: "601000.SH", name: "贵州测试" },
      ])
    ).toBe("600519.SH");
  });

  it("returns null when nothing matches", () => {
    expect(resolveSearchNavigation("xyz", [])).toBeNull();
  });
});
