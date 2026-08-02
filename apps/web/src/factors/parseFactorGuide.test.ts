/** parseFactorGuide：三段式标题拆分。 */
import { describe, expect, it } from "vitest";
import { parseFactorGuide } from "./parseFactorGuide";

describe("parseFactorGuide", () => {
  it("splits three titled sections", () => {
    const text = "【含义】甲\n【怎么用】乙\n【注意点】丙";
    expect(parseFactorGuide(text)).toEqual([
      { title: "含义", body: "甲" },
      { title: "怎么用", body: "乙" },
      { title: "注意点", body: "丙" },
    ]);
  });

  it("returns single untitled block when no markers", () => {
    expect(parseFactorGuide("普通说明")).toEqual([{ title: "", body: "普通说明" }]);
  });

  it("keeps trailing period note as part of last or extra paragraph", () => {
    const text = "【含义】甲\n【怎么用】乙\n【注意点】丙\n（本条目默认周期 14）";
    const parts = parseFactorGuide(text);
    expect(parts.some((p) => p.body.includes("本条目默认周期") || p.title === "")).toBe(true);
  });
});
