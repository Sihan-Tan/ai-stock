import { describe, expect, it } from "vitest";
import {
  ashareContinuousStartSlot,
  ashareSessionLastSlot,
  clampIntradayPollIntervalSec,
  INTRADAY_TIME_BASE,
  mapMinuteBarsToSlots,
  toAshareSessionSlot,
  upsertSlotPrice,
} from "./intradaySlots";

describe("clampIntradayPollIntervalSec", () => {
  it("clamps to 5–60 and falls back to 10 for invalid", () => {
    expect(clampIntradayPollIntervalSec(3)).toBe(5);
    expect(clampIntradayPollIntervalSec(100)).toBe(60);
    expect(clampIntradayPollIntervalSec(10)).toBe(10);
    expect(clampIntradayPollIntervalSec("x")).toBe(10);
  });
});

describe("toAshareSessionSlot", () => {
  it("groups seconds into slotSec buckets (S=10)", () => {
    const s = 10;
    expect(toAshareSessionSlot(9, 30, 0, s)).toBe(toAshareSessionSlot(9, 30, 9, s));
    expect(toAshareSessionSlot(9, 30, 10, s)).toBe(
      (toAshareSessionSlot(9, 30, 0, s) as number) + 1
    );
  });

  it("mirrors minute session boundaries", () => {
    expect(toAshareSessionSlot(9, 14, 0, 60)).toBeNull();
    expect(toAshareSessionSlot(12, 0, 0, 60)).toBeNull();
    expect(toAshareSessionSlot(9, 15, 0, 60)).toBe(0);
    expect(toAshareSessionSlot(15, 0, 0, 60)).toBe(255);
    // 11:30 与 13:00 共点
    expect(toAshareSessionSlot(11, 30, 0, 60)).toBe(toAshareSessionSlot(13, 0, 0, 60));
  });
});

describe("ashare session slot extents", () => {
  it("matches legacy minute axis when S=60", () => {
    expect(ashareSessionLastSlot(60)).toBe(255);
    expect(ashareContinuousStartSlot(60)).toBe(15);
  });
});

describe("mapMinuteBarsToSlots", () => {
  it("maps minute bars onto slot axis with last-write-wins", () => {
    expect(
      mapMinuteBarsToSlots(
        [
          {
            ts: "2026-07-15T01:15:00.000Z", // 09:15 CST
            open: 9.9,
            high: 10.1,
            low: 9.8,
            close: 10,
          },
          {
            ts: "2026-07-15T01:30:00.000Z", // 09:30 CST
            open: 10,
            high: 11,
            low: 9,
            close: 10.5,
            volume: 100,
          },
          {
            ts: "2026-07-15T03:30:00.000Z", // 11:30 CST
            open: 10.4,
            high: 10.5,
            low: 10.3,
            close: 10.4,
          },
          {
            ts: "2026-07-15T05:00:00.000Z", // 13:00 CST，与 11:30 同槽
            open: 10.6,
            high: 10.7,
            low: 10.4,
            close: 10.55,
          },
          {
            ts: "2026-07-15T04:00:00.000Z", // 12:00 午休
            open: 10,
            high: 10,
            low: 10,
            close: 10,
          },
        ],
        60
      )
    ).toEqual([
      {
        time: INTRADAY_TIME_BASE,
        open: 9.9,
        high: 10.1,
        low: 9.8,
        close: 10,
        value: 10,
        volume: 0,
      },
      {
        time: INTRADAY_TIME_BASE + 15,
        open: 10,
        high: 11,
        low: 9,
        close: 10.5,
        value: 10.5,
        volume: 100,
      },
      {
        time: INTRADAY_TIME_BASE + 135,
        open: 10.6,
        high: 10.7,
        low: 10.4,
        close: 10.55,
        value: 10.55,
        volume: 0,
      },
    ]);
  });
});

describe("upsertSlotPrice", () => {
  it("inserts or updates close/value at BASE+slotIndex", () => {
    const next = upsertSlotPrice([], 90, 12.3);
    expect(next).toEqual([
      {
        time: INTRADAY_TIME_BASE + 90,
        open: 12.3,
        high: 12.3,
        low: 12.3,
        close: 12.3,
        value: 12.3,
      },
    ]);
    const updated = upsertSlotPrice(next, 90, 12.5);
    expect(updated).toHaveLength(1);
    expect(updated[0].close).toBe(12.5);
    expect(updated[0].value).toBe(12.5);
  });
});
