import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AssistantMessageBody } from "./AssistantMessageBody";

const tableMd = `| 指标 | 数值 |
| --- | --- |
| PE | 28 |`;

describe("AssistantMessageBody", () => {
  it("keeps plain text while streaming", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, { content: tableMd, streaming: true }),
    );
    expect(html).not.toContain("<table");
    expect(html).toContain("<pre");
  });

  it("renders markdown table when done", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, { content: tableMd, streaming: false }),
    );
    expect(html).toContain("<table");
  });

  it("renders json panel for whole-message JSON", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, {
        content: '{"symbol":"600519"}',
        streaming: false,
      }),
    );
    expect(html).toContain("JSON");
    expect(html).toContain("600519");
  });

  it("shows ellipsis placeholder when streaming empty", () => {
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, { content: "", streaming: true }),
    );
    expect(html).toContain("…");
  });

  it("does not nest pre for fenced code blocks", () => {
    const md = "```js\nconst x = 1;\n```";
    const html = renderToStaticMarkup(
      createElement(AssistantMessageBody, { content: md, streaming: false }),
    );
    expect(html).not.toMatch(/<pre[^>]*>[\s\S]*<pre/);
    expect(html).toContain("research-md-pre");
  });
});
