import { describe, expect, it } from "vitest";
import {
  buildMacdSeries,
  buildSmaSeries,
  formatAshareSessionLabel,
  formatDailyCrosshairTime,
  formatIntradayCrosshairTime,
  summarizeIntradayBars,
  toAshareSessionIndex,
  toChartBars,
} from "./format";

describe("toChartBars", () => {
  it("converts daily bars to business-day candlestick data", () => {
    expect(
      toChartBars(
        [
          {
            date: "2026-07-15",
            open: 10,
            high: 11,
            low: 9,
            close: 10.5,
            volume: 100,
          },
        ],
        "day"
      )
    ).toEqual([
      {
        time: "2026-07-15",
        open: 10,
        high: 11,
        low: 9,
        close: 10.5,
        value: 10.5,
        volume: 100,
      },
    ]);
  });

  it("maps intraday bars onto continuous A-share session axis", () => {
    expect(
      toChartBars(
        [
          {
            ts: "2026-07-15T01:30:00.000Z", // 09:30 CST
            open: 10,
            high: 11,
            low: 9,
            close: 10.5,
          },
          {
            ts: "2026-07-15T03:30:00.000Z", // 11:30 CST
            open: 10.4,
            high: 10.5,
            low: 10.3,
            close: 10.4,
          },
          {
            ts: "2026-07-15T05:00:00.000Z", // 13:00 CST，与 11:30 同点
            open: 10.6,
            high: 10.7,
            low: 10.4,
            close: 10.55,
          },
          {
            ts: "2026-07-15T04:00:00.000Z", // 12:00 午休，应丢弃
            open: 10,
            high: 10,
            low: 10,
            close: 10,
          },
        ],
        "intraday"
      )
    ).toEqual([
      {
        time: 1_000_000,
        open: 10,
        high: 11,
        low: 9,
        close: 10.5,
        value: 10.5,
        volume: 0,
      },
      {
        time: 1_000_120,
        open: 10.6,
        high: 10.7,
        low: 10.4,
        close: 10.55,
        value: 10.55,
        volume: 0,
      },
    ]);
  });

  it("excludes bars that lack a valid time", () => {
    expect(
      toChartBars([{ open: 10, high: 11, low: 9, close: 10.5 }], "day")
    ).toEqual([]);
  });
});

describe("ashare session axis", () => {
  it("maps morning and afternoon onto continuous indexes", () => {
    expect(toAshareSessionIndex(9, 30)).toBe(0);
    expect(toAshareSessionIndex(11, 30)).toBe(120);
    expect(toAshareSessionIndex(13, 0)).toBe(120);
    expect(toAshareSessionIndex(15, 0)).toBe(240);
    expect(toAshareSessionIndex(12, 0)).toBeNull();
  });

  it("formats key session labels", () => {
    expect(formatAshareSessionLabel(0)).toBe("09:30");
    expect(formatAshareSessionLabel(120)).toBe("11:30/13:00");
    expect(formatAshareSessionLabel(240)).toBe("15:00");
  });

  it("formats intraday crosshair as HH:mm", () => {
    expect(formatIntradayCrosshairTime(1_000_000 as never)).toBe("09:30");
    expect(formatIntradayCrosshairTime(1_000_031 as never)).toBe("10:01");
    expect(formatIntradayCrosshairTime(1_000_120 as never)).toBe("11:30/13:00");
  });
});

describe("formatDailyCrosshairTime", () => {
  it("formats business day as MM-DD", () => {
    expect(formatDailyCrosshairTime("2026-07-15")).toBe("07-15");
    expect(formatDailyCrosshairTime({ year: 2026, month: 7, day: 15 })).toBe("07-15");
  });
});

describe("buildSmaSeries", () => {
  it("computes simple moving averages", () => {
    const bars = [
      { time: "2026-01-01", open: 1, high: 1, low: 1, close: 1, value: 1 },
      { time: "2026-01-02", open: 2, high: 2, low: 2, close: 2, value: 2 },
      { time: "2026-01-03", open: 3, high: 3, low: 3, close: 3, value: 3 },
      { time: "2026-01-04", open: 4, high: 4, low: 4, close: 4, value: 4 },
    ];
    expect(buildSmaSeries(bars as never, 3)).toEqual([
      { time: "2026-01-03", value: 2 },
      { time: "2026-01-04", value: 3 },
    ]);
  });
});

describe("buildMacdSeries", () => {
  it("returns DIF/DEA/hist from the first bar", () => {
    const bars = Array.from({ length: 40 }, (_, index) => {
      const close = 10 + index * 0.2;
      return {
        time: `2026-01-${String(index + 1).padStart(2, "0")}`,
        open: close,
        high: close,
        low: close,
        close,
        value: close,
      };
    });
    const points = buildMacdSeries(bars as never);
    expect(points.length).toBe(40);
    expect(points[0].time).toBe(bars[0].time);
    const latest = points[points.length - 1];
    expect(latest.dif).toBeGreaterThan(0);
    expect(latest.dea).toBeGreaterThan(0);
    expect(latest.hist).toBeCloseTo(latest.dif - latest.dea, 8);
  });

  it("returns empty when bars are insufficient", () => {
    expect(
      buildMacdSeries([
        { time: "2026-01-01", open: 1, high: 1, low: 1, close: 1, value: 1 },
      ] as never)
    ).toEqual([]);
  });
});

describe("summarizeIntradayBars", () => {
  it("computes VWAP and OHLC from minute bars", () => {
    expect(
      summarizeIntradayBars([
        {
          ts: "2026-07-15T01:31:00.000Z",
          open: 10.2,
          high: 10.5,
          low: 10.1,
          close: 10.4,
          volume: 100,
          amount: 1040,
        },
        {
          ts: "2026-07-15T01:30:00.000Z",
          open: 10,
          high: 10.3,
          low: 9.9,
          close: 10.2,
          volume: 100,
          amount: 1020,
        },
      ])
    ).toEqual({
      avg: 10.3,
      open: 10,
      close: 10.4,
      high: 10.5,
      low: 9.9,
    });
  });

  it("treats volume as lots when amount/volume is far above price", () => {
    // amount 元、volume 手：amount/volume=102000，应折算为 amount/(volume*100)=1020
    const summary = summarizeIntradayBars([
      {
        ts: "2026-07-15T01:30:00.000Z",
        open: 1000,
        high: 1020,
        low: 990,
        close: 1010,
        volume: 10,
        amount: 1_020_000,
      },
    ]);
    expect(summary.avg).toBeCloseTo(1020, 5);
  });

  it("returns nulls for empty bars", () => {
    expect(summarizeIntradayBars([])).toEqual({
      avg: null,
      open: null,
      close: null,
      high: null,
      low: null,
    });
  });
});
