import { describe, expect, it } from "vitest";
import { parseSearchSymbol } from "./parseSearchSymbol";

describe("parseSearchSymbol", () => {
  it("maps 6-digit Shanghai codes to .SH", () => {
    expect(parseSearchSymbol("600519")).toBe("600519.SH");
  });

  it("maps 6-digit Shenzhen codes to .SZ", () => {
    expect(parseSearchSymbol("000001")).toBe("000001.SZ");
  });

  it("keeps already qualified symbols", () => {
    expect(parseSearchSymbol("000001.SZ")).toBe("000001.SZ");
  });

  it("returns null for empty input", () => {
    expect(parseSearchSymbol("")).toBeNull();
    expect(parseSearchSymbol("   ")).toBeNull();
  });

  it("returns null for invalid formats", () => {
    expect(parseSearchSymbol("ABC")).toBeNull();
    expect(parseSearchSymbol("12345")).toBeNull();
  });
});
