import { describe, expect, it } from "vitest";
import { buildChatMessages } from "./researchMessages";

describe("buildChatMessages", () => {
  it("appends the new user turn after history", () => {
    expect(
      buildChatMessages(
        [
          { role: "user", content: "你好" },
          { role: "assistant", content: "请说" },
        ],
        "分析茅台",
      ),
    ).toEqual([
      { role: "user", content: "你好" },
      { role: "assistant", content: "请说" },
      { role: "user", content: "分析茅台" },
    ]);
  });

  it("works with empty history", () => {
    expect(buildChatMessages([], "单独提问")).toEqual([{ role: "user", content: "单独提问" }]);
  });
});
