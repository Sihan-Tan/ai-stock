import { describe, expect, it } from "vitest";
import { smaTdx, hhv, llv, refAt, filterSignal } from "./tdxMath";

describe("smaTdx", () => {
  it("uses recursive Y=(X+(N-1)*Yprev)/N", () => {
    // N=3, M=1: y0=x0; y1=(x1+2*y0)/3; y2=(x2+2*y1)/3
    const y = smaTdx([3, 6, 9], 3);
    expect(y[0]).toBeCloseTo(3, 8);
    expect(y[1]).toBeCloseTo((6 + 2 * 3) / 3, 8);
    expect(y[2]).toBeCloseTo((9 + 2 * y[1]) / 3, 8);
  });
});

describe("hhv/llv", () => {
  it("rolling max/min over window", () => {
    expect(hhv([1, 3, 2, 5], 2)).toEqual([1, 3, 3, 5]);
    expect(llv([1, 3, 2, 5], 2)).toEqual([1, 1, 2, 2]);
  });
});

describe("refAt", () => {
  it("looks back N bars", () => {
    expect(refAt([10, 20, 30], 2, 1)).toBe(20);
    expect(refAt([10, 20, 30], 0, 1)).toBeNull();
  });
});

describe("filterSignal", () => {
  it("suppresses repeats within N bars", () => {
    const cond = [false, true, true, false, true];
    // N=2: fire at i=1, suppress i=2, fire at i=4
    expect(filterSignal(cond, 2)).toEqual([false, true, false, false, true]);
  });
});
