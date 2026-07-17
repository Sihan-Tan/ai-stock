import { describe, expect, it } from "vitest";
import {
  buildSmaSeries,
  formatAshareSessionLabel,
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
            ts: "2026-07-15T05:00:00.000Z", // 13:00 CST
            open: 10.6,
            high: 10.7,
            low: 10.4,
            close: 10.5,
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
      },
      {
        time: 1_000_121,
        open: 10.6,
        high: 10.7,
        low: 10.4,
        close: 10.5,
        value: 10.5,
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
    expect(toAshareSessionIndex(13, 0)).toBe(121);
    expect(toAshareSessionIndex(15, 0)).toBe(241);
    expect(toAshareSessionIndex(12, 0)).toBeNull();
  });

  it("formats session labels", () => {
    expect(formatAshareSessionLabel(0)).toBe("09:30");
    expect(formatAshareSessionLabel(120)).toBe("11:30");
    expect(formatAshareSessionLabel(121)).toBe("13:00");
    expect(formatAshareSessionLabel(241)).toBe("15:00");
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
