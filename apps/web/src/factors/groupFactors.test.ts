import { describe, expect, it } from "vitest";
import { groupFactorCatalog } from "./groupFactors";
import type { FactorMeta } from "./types";

const sample: FactorMeta[] = [
  { name: "SMA_20", label: "SMA 20", category: "trend", params: {}, outputs: ["sma_20"], plot: "overlay", default_enabled: true, enabled: true },
  { name: "SMA_10", label: "SMA 10", category: "trend", params: {}, outputs: ["sma_10"], plot: "overlay", default_enabled: false, enabled: true },
  { name: "RSI_14", label: "RSI 14", category: "momentum", params: {}, outputs: ["rsi_14"], plot: "panel", default_enabled: true, enabled: true },
  { name: "WILLR_14", label: "WILLR", category: "momentum", params: {}, outputs: ["willr_14"], plot: "panel", default_enabled: false, enabled: true },
];

describe("groupFactorCatalog", () => {
  it("splits selected vs collapsed categories for unselected", () => {
    const selected = new Set(["SMA_20", "RSI_14"]);
    const g = groupFactorCatalog(sample, selected);
    expect(g.selected.map((f) => f.name)).toEqual(["SMA_20", "RSI_14"]);
    expect(g.collapsedCategories.map((c) => c.category)).toEqual(["trend", "momentum"]);
    expect(g.collapsedCategories.find((c) => c.category === "trend")!.items.map((i) => i.name)).toEqual(["SMA_10"]);
  });
});
