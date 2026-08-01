import { describe, expect, it } from "vitest";
import {
  MAIN_OVERLAYS,
  listOverlaysForPeriod,
  shouldShowMainOverlaySelect,
  buildSmaOverlayLines,
  buildMaTacticOverlayLines,
  buildIntradayDipOverlay,
  buildMainOverlay,
  getMainOverlay,
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
  it("shows for day/week/month and intraday", () => {
    expect(shouldShowMainOverlaySelect("day")).toBe(true);
    expect(shouldShowMainOverlaySelect("week")).toBe(true);
    expect(shouldShowMainOverlaySelect("month")).toBe(true);
    expect(shouldShowMainOverlaySelect("intraday")).toBe(true);
  });
});

describe("listOverlaysForPeriod", () => {
  it("lists sma and ma_tactic for day and none/dip for intraday", () => {
    const day = listOverlaysForPeriod("day");
    expect(day.map((o) => o.id)).toEqual(["sma", "ma_tactic"]);
    expect(day[0].label).toBe("移动均线");
    expect(day[1].label).toBe("均线战法");
    expect(listOverlaysForPeriod("intraday").map((o) => o.id)).toEqual([
      "none",
      "intraday_dip",
    ]);
  });

  it("registry includes sma, ma_tactic, none, intraday_dip", () => {
    expect(MAIN_OVERLAYS.map((o) => o.id)).toEqual([
      "sma",
      "ma_tactic",
      "none",
      "intraday_dip",
    ]);
  });
});

describe("intraday registry", () => {
  it("lists none and intraday_dip", () => {
    expect(listOverlaysForPeriod("intraday").map((o) => o.id)).toEqual([
      "none",
      "intraday_dip",
    ]);
    expect(shouldShowMainOverlaySelect("intraday")).toBe(true);
  });
});

describe("buildIntradayDipOverlay", () => {
  it("computes support/resistance and strength stick colors", () => {
    /**
     * 构造两日分钟：昨日 40 根 close=10，今日 5 根递增；preClose=10。
     * @param ts ISO 时间
     * @param close 收盘价
     * @param high 最高价
     * @param low 最低价
     */
    const mk = (ts: string, close: number, high?: number, low?: number): OhlcvBar => ({
      ts,
      open: close,
      high: high ?? close,
      low: low ?? close,
      close,
      volume: 100,
    });
    const calc: OhlcvBar[] = [];
    for (let i = 0; i < 40; i += 1) {
      const mm = 31 + (i % 20);
      calc.push(mk(`2026-07-24T09:${String(mm).padStart(2, "0")}:00+08:00`, 10));
    }
    // 今日：抬高低点，便于验支撑阻力
    calc.push(mk("2026-07-27T09:31:00+08:00", 10, 12, 8));
    calc.push(mk("2026-07-27T09:32:00+08:00", 10.5, 12, 8));
    calc.push(mk("2026-07-27T09:33:00+08:00", 11, 12, 8));
    calc.push(mk("2026-07-27T09:34:00+08:00", 9, 12, 8));
    calc.push(mk("2026-07-27T09:35:00+08:00", 9.2, 12, 8));

    const dayBars = calc.filter((b) => b.ts!.startsWith("2026-07-27"));
    const chartBars = toChartBars(dayBars, "intraday");
    const result = buildIntradayDipOverlay({
      chartBars,
      calcBars: calc,
      preClose: 10,
      sessionDate: "2026-07-27",
    });

    expect(result.lines.map((l) => l.label).sort()).toEqual(
      ["MA30", "支撑", "强弱", "阻力"].sort()
    );
    // H1=max(10,12)=12, L1=min(10,8)=8, P1=4
    // 阻力=8+4*7/8=11.5, 支撑=8+4*0.5/8=8.25
    const resist = result.lines.find((l) => l.label === "阻力")!;
    const support = result.lines.find((l) => l.label === "支撑")!;
    expect(resist.points[resist.points.length - 1].value).toBeCloseTo(11.5, 8);
    expect(support.points[support.points.length - 1].value).toBeCloseTo(8.25, 8);
    expect(result.sticks.length).toBeGreaterThan(0);
  });

  it("none build returns empty", () => {
    const empty = buildMainOverlay(getMainOverlay("none"), {
      chartBars: [],
    });
    expect(empty).toEqual({ lines: [], sticks: [], markers: [] });
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
