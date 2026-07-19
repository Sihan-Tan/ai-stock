import { describe, expect, it } from "vitest";
import { detectContentKind, formatJsonText, JSON_COLLAPSE_THRESHOLD } from "./detectContentKind";

describe("detectContentKind", () => {
  it("detects object and array JSON", () => {
    expect(detectContentKind('{"a":1}')).toBe("json");
    expect(detectContentKind("  [1, 2]  ")).toBe("json");
  });

  it("treats invalid JSON and markdown as markdown", () => {
    expect(detectContentKind("{not json")).toBe("markdown");
    expect(detectContentKind("## 标题\n- 列表")).toBe("markdown");
    expect(detectContentKind("")).toBe("markdown");
  });
});

describe("formatJsonText", () => {
  it("pretty-prints valid JSON", () => {
    expect(formatJsonText('{"a":1}')).toBe('{\n  "a": 1\n}');
  });

  it("returns original text when parse fails", () => {
    expect(formatJsonText("{x")).toBe("{x");
  });
});

describe("JSON_COLLAPSE_THRESHOLD", () => {
  it("is 100KB", () => {
    expect(JSON_COLLAPSE_THRESHOLD).toBe(100_000);
  });
});
