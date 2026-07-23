/** dumpFactorRulesYaml / parseFactorRulesYaml 轻量单测（纯函数）。 */
import { describe, expect, it } from "vitest";
import {
  dumpFactorRulesYaml,
  formatFactorOptionLabel,
  parseFactorRulesYaml,
} from "../pages/StrategyRuleBuilder";

describe("formatFactorOptionLabel", () => {
  it("formats name with distinct tip", () => {
    expect(formatFactorOptionLabel("RSI_14", "RSI")).toBe("RSI_14（RSI）");
  });

  it("prefers description over label", () => {
    expect(formatFactorOptionLabel("RSI_14", "RSI", "相对强弱指数 RSI")).toBe(
      "RSI_14（相对强弱指数 RSI）"
    );
  });

  it("keeps nested tip for ml factor", () => {
    expect(formatFactorOptionLabel("ml:x", "x（lightgbm）")).toBe("ml:x（x（lightgbm））");
  });

  it("returns name when tip equals name", () => {
    expect(formatFactorOptionLabel("SMA_20", "SMA_20")).toBe("SMA_20");
  });
});

describe("parseFactorRulesYaml PyYAML dump", () => {
  it("parses conditions when list item does not start with op", () => {
    const yaml = `id: rule_ut
name: test
version: v1.0
kind: factor_rules
buy:
  combine: all
  conditions:
  - left:
      factor: SMA_5
    op: cross_up
    right:
      factor: SMA_20
sell:
  combine: any
  conditions:
  - left:
      factor: RSI_14
    op: gt
    right:
      const: 70
`;
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed).not.toBeNull();
    expect(parsed?.buy.conditions).toHaveLength(1);
    expect(parsed?.buy.conditions[0]?.op).toBe("cross_up");
    expect(parsed?.buy.conditions[0]?.left).toEqual({ kind: "factor", factor: "SMA_5" });
    expect(parsed?.buy.conditions[0]?.right).toEqual({ kind: "factor", factor: "SMA_20" });
    expect(parsed?.sell.conditions).toHaveLength(1);
    expect(parsed?.sell.conditions[0]?.op).toBe("gt");
    expect(parsed?.sell.conditions[0]?.right).toEqual({ kind: "const", const: 70 });
  });
});

describe("factor rules yaml roundtrip", () => {
  it("dumps kind factor_rules and parses back", () => {
    const yaml = dumpFactorRulesYaml({
      id: "rule_ut",
      name: "单测规则",
      version: "v1.0",
      kind: "factor_rules",
      buy: {
        combine: "all",
        conditions: [
          {
            op: "lt",
            left: { kind: "factor", factor: "RSI_14" },
            right: { kind: "const", const: 30 },
          },
        ],
      },
      sell: {
        combine: "any",
        conditions: [
          {
            op: "cross_down",
            left: { kind: "factor", factor: "SMA_5" },
            right: { kind: "factor", factor: "SMA_20" },
          },
        ],
      },
    });
    expect(yaml).toContain("kind: factor_rules");
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed).not.toBeNull();
    expect(parsed?.id).toBe("rule_ut");
    expect(parsed?.buy.combine).toBe("all");
    expect(parsed?.buy.conditions[0]?.op).toBe("lt");
    expect(parsed?.buy.conditions[0]?.right).toEqual({ kind: "const", const: 30 });
    expect(parsed?.sell.conditions[0]?.op).toBe("cross_down");
  });

  it("dumps and parses near_pct with pct", () => {
    const yaml = dumpFactorRulesYaml({
      id: "rule_near",
      name: "贴近均线",
      version: "v1.0",
      kind: "factor_rules",
      buy: {
        combine: "all",
        conditions: [
          {
            op: "near_pct",
            left: { kind: "factor", factor: "CLOSE" },
            right: { kind: "factor", factor: "SMA_20" },
            pct: 3,
          },
        ],
      },
      sell: { combine: "any", conditions: [] },
    });
    expect(yaml).toContain("op: near_pct");
    expect(yaml).toContain("pct: 3");
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed?.buy.conditions[0]?.op).toBe("near_pct");
    expect(parsed?.buy.conditions[0]?.pct).toBe(3);
    expect(parsed?.buy.conditions[0]?.left).toEqual({ kind: "factor", factor: "CLOSE" });
  });
});
