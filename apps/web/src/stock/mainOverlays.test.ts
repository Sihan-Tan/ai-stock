import { describe, expect, it } from "vitest";
import {
  MAIN_OVERLAYS,
  listOverlaysForPeriod,
  shouldShowMainOverlaySelect,
  buildSmaOverlayLines,
  buildMaTacticOverlayLines,
} from "./mainOverlays";
import {
  buildEmaSeries,
  buildSmaSeries,
  buildStdSeries,
  DAILY_MA_LINES,
  toChartBars,
} from "./format";
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
  it("lists sma and ma_tactic for day and empty for intraday", () => {
    const day = listOverlaysForPeriod("day");
    expect(day.map((o) => o.id)).toEqual(["sma", "ma_tactic"]);
    expect(day[0].label).toBe("移动均线");
    expect(day[1].label).toBe("均线战法");
    expect(listOverlaysForPeriod("intraday")).toEqual([]);
  });

  it("registry includes sma and ma_tactic", () => {
    expect(MAIN_OVERLAYS.map((o) => o.id)).toEqual(["sma", "ma_tactic"]);
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

describe("buildMaTacticOverlayLines", () => {
  it("builds bands and emas with expected labels and thicknesses", () => {
    const raw: OhlcvBar[] = Array.from({ length: 160 }, (_, i) => ({
      date: `2026-${String(Math.floor(i / 28) + 1).padStart(2, "0")}-${String((i % 28) + 1).padStart(2, "0")}`,
      open: 10,
      high: 11,
      low: 9,
      close: 10 + (i % 7),
      volume: 1,
    }));
    const chartBars = toChartBars(raw, "day");
    const lines = buildMaTacticOverlayLines(chartBars);
    expect(lines.map((l) => l.label)).toEqual([
      "上轨",
      "上上轨",
      "生命线",
      "下下轨",
      "下轨",
      "红",
      "绿",
    ]);
    const red = lines.find((l) => l.label === "红");
    const green = lines.find((l) => l.label === "绿");
    expect(red?.lineWidth).toBe(3);
    expect(green?.lineWidth).toBe(2);
    expect(red?.points).toEqual(buildEmaSeries(chartBars, 7));
    expect(green?.points).toEqual(buildEmaSeries(chartBars, 20));

    const ma60 = buildSmaSeries(chartBars, 60);
    const std60 = buildStdSeries(chartBars, 60);
    const upper = lines.find((l) => l.label === "上轨");
    expect(upper?.points.length).toBe(ma60.length);
    expect(upper?.points[0].value).toBeCloseTo(ma60[0].value + 2 * std60[0].value, 8);
  });
});
