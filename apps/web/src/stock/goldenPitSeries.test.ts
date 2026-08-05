/** 日 K 是否应加载黄金坑套件。 */
import { describe, expect, it } from "vitest";
import { shouldLoadGoldenPit, type GoldenPitOutputs } from "./goldenPitSeries";

describe("shouldLoadGoldenPit", () => {
  it("only day", () => {
    expect(shouldLoadGoldenPit("day")).toBe(true);
    expect(shouldLoadGoldenPit("week")).toBe(false);
    expect(shouldLoadGoldenPit("month")).toBe(false);
    expect(shouldLoadGoldenPit("intraday")).toBe(false);
  });
});

describe("pickGoldenPitOutputs", () => {
  it("reads nested series block", async () => {
    const { pickGoldenPitOutputs } = await import("./goldenPitSeries");
    const raw = {
      series: {
        GOLDEN_PIT: {
          outputs: {
            gp_line: [{ date: "2020-01-02", v: 1 }],
            gp_pit: [{ date: "2020-01-02", v: 0 }],
            gp_blowoff: [{ date: "2020-01-02", v: 50 }],
          },
        },
      },
    };
    const out = pickGoldenPitOutputs(raw) as GoldenPitOutputs;
    expect(out.gp_line).toHaveLength(1);
    expect(out.gp_blowoff[0]?.v).toBe(50);
  });
});
