import { describe, expect, it } from "vitest";
import { buildIntradayFundFlow } from "./intradayFundFlow";
import type { OhlcvBar } from "./types";

/**
 * 构造一根分钟 OHLCV。
 * @param ts ISO 时间
 * @param close 收盘价
 * @param high 最高价
 * @param low 最低价
 */
function mk(
  ts: string,
  close: number,
  high = close + 0.2,
  low = close - 0.2,
): OhlcvBar {
  return {
    ts,
    open: close,
    high,
    low,
    close,
    volume: 1000,
  };
}

/**
 * 生成跨昨今两日、合计 ≥60 根的单调上涨分钟线（含午后时段）。
 * @param sessionDate 会话日 YYYY-MM-DD
 * @param prevDate 预热日 YYYY-MM-DD
 * @param count 总根数
 */
function buildStockFixture(
  sessionDate: string,
  prevDate: string,
  count = 80,
): OhlcvBar[] {
  const bars: OhlcvBar[] = [];
  const half = Math.floor(count / 2);
  for (let i = 0; i < half; i += 1) {
    const minute = 31 + (i % 29);
    const hour = 9 + Math.floor(i / 29);
    const close = 10 + i * 0.05;
    bars.push(
      mk(
        `${prevDate}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00+08:00`,
        close,
      ),
    );
  }
  for (let i = 0; i < count - half; i += 1) {
    const minute = 31 + (i % 29);
    const hour = 9 + Math.floor(i / 29);
    const close = 12 + i * 0.08;
    bars.push(
      mk(
        `${sessionDate}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00+08:00`,
        close,
      ),
    );
  }
  return bars;
}

/**
 * 为个股 bars 生成同分钟对齐的指数 bars。
 * @param stockBars 个股分钟线
 * @param scale 指数价格相对个股的倍数
 */
function alignIndexBars(stockBars: OhlcvBar[], scale = 300): OhlcvBar[] {
  return stockBars.map((b) =>
    mk(b.ts!, b.close * scale, b.high * scale, b.low * scale),
  );
}

const SESSION = "2026-07-31";
const PREV = "2026-07-30";

describe("buildIntradayFundFlow", () => {
  it("builds trend line and main-force hist without index", () => {
    const stockBars = buildStockFixture(SESSION, PREV, 80);
    const result = buildIntradayFundFlow({
      stockBars,
      indexBars: [],
      sessionDate: SESSION,
    });

    const trend = result.lines.find((l) => l.label === "趋势线");
    expect(trend).toBeDefined();
    expect(trend!.points.length).toBeGreaterThan(0);
    const last = trend!.points[trend!.points.length - 1]!;
    expect(Number.isFinite(last.value)).toBe(true);

    const colors = new Set(result.hists.map((h) => h.color));
    const hasMainForce =
      colors.has("#FF00FF") || colors.has("#0000FF");
    expect(hasMainForce).toBe(true);

    const indexColors = result.hists.filter(
      (h) => h.color === "#EF4444" || h.color === "#22C55E",
    );
    expect(indexColors).toHaveLength(0);
  });

  it("adds index fund hists when indexBars align", () => {
    const stockBars = buildStockFixture(SESSION, PREV, 80);
    const indexBars = alignIndexBars(stockBars);
    const result = buildIntradayFundFlow({
      stockBars,
      indexBars,
      sessionDate: SESSION,
    });

    const indexHists = result.hists.filter(
      (h) => h.color === "#EF4444" || h.color === "#22C55E",
    );
    expect(indexHists.length).toBeGreaterThan(0);

    const sessionStockCount = stockBars.filter((b) =>
      b.ts!.startsWith(SESSION),
    ).length;
    expect(indexHists.length).toBeLessThanOrEqual(sessionStockCount);
  });

  it("does not throw when indexBars empty", () => {
    const fixture = buildStockFixture(SESSION, PREV, 80);
    expect(() =>
      buildIntradayFundFlow({
        stockBars: fixture,
        indexBars: [],
        sessionDate: SESSION,
      }),
    ).not.toThrow();
  });
});
