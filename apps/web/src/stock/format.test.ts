import { describe, expect, it } from "vitest";
import { toChartBars } from "./format";

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
      toChartBars(
        [{ open: 10, high: 11, low: 9, close: 10.5 }],
        "day"
      )
    ).toEqual([]);
  });
});
