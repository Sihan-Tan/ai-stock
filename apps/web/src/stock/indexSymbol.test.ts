import { describe, expect, it } from "vitest";
import { resolveIndexSymbol } from "./indexSymbol";

describe("resolveIndexSymbol", () => {
  it("maps SH to SSE composite", () => {
    expect(resolveIndexSymbol("600519.SH")).toBe("000001.SH");
    expect(resolveIndexSymbol("688981.SH")).toBe("000001.SH");
  });

  it("maps SZ (incl. ChiNext) to SZSE component", () => {
    expect(resolveIndexSymbol("000001.SZ")).toBe("399001.SZ");
    expect(resolveIndexSymbol("300750.SZ")).toBe("399001.SZ");
  });

  it("returns null for unknown suffix", () => {
    expect(resolveIndexSymbol("FOO")).toBeNull();
  });
});
