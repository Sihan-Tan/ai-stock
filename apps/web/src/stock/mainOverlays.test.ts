import { describe, expect, it } from "vitest";
import {
  MAIN_OVERLAYS,
  listOverlaysForPeriod,
  shouldShowMainOverlaySelect,
  buildSmaOverlayLines,
} from "./mainOverlays";
import { buildSmaSeries, DAILY_MA_LINES, toChartBars } from "./format";
import type { OhlcvBar } from "./types";

describe("shouldShowMainOverlaySelect", () => {
  it("shows for day/week/month only", () => {
    expect(shouldShowMainOverlaySelect("day")).toBe(true);
    expect(shouldShowMainOverlaySelect("week")).toBe(true);
    expect(shouldShowMainOverlaySelect("month")).toBe(true);
    expect(shouldShowMainOverlaySelect("intraday")).toBe(false);
  });
});

describe("listOverlaysForPeriod", () => {
  it("lists sma for day and empty for intraday", () => {
    const day = listOverlaysForPeriod("day");
    expect(day.map((o) => o.id)).toEqual(["sma"]);
    expect(day[0].label).toBe("移动均线");
    expect(listOverlaysForPeriod("intraday")).toEqual([]);
  });

  it("registry has only sma in v1", () => {
    expect(MAIN_OVERLAYS.map((o) => o.id)).toEqual(["sma"]);
  });
});

describe("buildSmaOverlayLines", () => {
  it("matches buildSmaSeries for each window", () => {
    const raw: OhlcvBar[] = Array.from({ length: 10 }, (_, i) => ({
      date: `2026-01-${String(i + 1).padStart(2, "0")}`,
      open: 10,
      high: 11,
      low: 9,
      close: 10 + i,
      volume: 1,
    }));
    const chartBars = toChartBars(raw, "day");
    const lines = buildSmaOverlayLines(chartBars);
    expect(lines).toHaveLength(DAILY_MA_LINES.length);
    for (let i = 0; i < DAILY_MA_LINES.length; i += 1) {
      const expectPts = buildSmaSeries(chartBars, DAILY_MA_LINES[i].window);
      expect(lines[i].label).toBe(DAILY_MA_LINES[i].label);
      expect(lines[i].color).toBe(DAILY_MA_LINES[i].color);
      expect(lines[i].points).toEqual(expectPts);
    }
  });
});
