import { describe, expect, it } from "vitest";
import { formatSnippet } from "./Knowledge";

describe("formatSnippet", () => {
  it("空内容返回占位", () => {
    expect(formatSnippet("")).toBe("（无摘要）");
    expect(formatSnippet(undefined)).toBe("（无摘要）");
    expect(formatSnippet("   \n\t  ")).toBe("（无摘要）");
  });

  it("短文本原样返回并压缩空白", () => {
    expect(formatSnippet("晋级率  与  情绪")).toBe("晋级率 与 情绪");
  });

  it("超长截断并加省略号", () => {
    const long = "字".repeat(130);
    const out = formatSnippet(long, 120);
    expect(out).toHaveLength(121);
    expect(out.endsWith("…")).toBe(true);
    expect(out.slice(0, 120)).toBe("字".repeat(120));
  });
});
