import { describe, expect, it } from "vitest";
import {
  crossUp,
  longCrossUp,
  shiftTradingDaysBack,
  beijingDateFromTs,
  filterBarsOnBeijingDate,
} from "./overlayMath";
import type { OhlcvBar } from "./types";

describe("crossUp", () => {
  it("detects A crossing above B", () => {
    expect(crossUp([1, 1, 3], [2, 2, 2], 2)).toBe(true);
    expect(crossUp([1, 1, 1], [2, 2, 2], 2)).toBe(false);
    expect(crossUp([3, 3, 3], [2, 2, 2], 2)).toBe(false);
  });
});

describe("longCrossUp", () => {
  it("requires stay above for N bars after cross", () => {
    // i=2: 1→3 上穿 2；i=3 仍 > → LONGCROSS(...,2) 在 i=3 为 true
    expect(longCrossUp([1, 1, 3, 4], [2, 2, 2, 2], 3, 2)).toBe(true);
    expect(longCrossUp([1, 1, 3, 1], [2, 2, 2, 2], 3, 2)).toBe(false);
    expect(longCrossUp([1, 1, 3], [2, 2, 2], 2, 2)).toBe(false);
  });
});

describe("shiftTradingDaysBack", () => {
  it("skips weekends", () => {
    // 2026-07-27 周一；回推 1 个交易日 → 2026-07-24 周五
    expect(shiftTradingDaysBack("2026-07-27", 1)).toBe("2026-07-24");
    // 回推 5 个交易日：26=周日跳过… → 2026-07-20 周一
    expect(shiftTradingDaysBack("2026-07-27", 5)).toBe("2026-07-20");
  });
});

describe("filterBarsOnBeijingDate", () => {
  it("keeps bars on the given Beijing calendar day", () => {
    const bars: OhlcvBar[] = [
      {
        ts: "2026-07-27T09:31:00+08:00",
        open: 1,
        high: 1,
        low: 1,
        close: 1,
        volume: 1,
      },
      {
        ts: "2026-07-28T09:31:00+08:00",
        open: 2,
        high: 2,
        low: 2,
        close: 2,
        volume: 1,
      },
    ];
    expect(filterBarsOnBeijingDate(bars, "2026-07-27")).toHaveLength(1);
    expect(beijingDateFromTs("2026-07-27T15:00:00+08:00")).toBe("2026-07-27");
  });
});
