import { describe, expect, it } from "vitest";
import { buildSmaSeries, summarizeIntradayBars, toChartBars } from "./format";

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

  it("converts ISO intraday timestamps to unix seconds", () => {
    expect(
      toChartBars(
        [
          {
            ts: "2026-07-15T01:30:00.000Z",
            open: 10,
            high: 11,
            low: 9,
            close: 10.5,
          },
        ],
        "intraday"
      )
    ).toEqual([
      {
        time: 1784079000,
        open: 10,
        high: 11,
        low: 9,
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
