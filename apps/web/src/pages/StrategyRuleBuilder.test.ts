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

  it("keeps nested tip for ml factor", () => {
    expect(formatFactorOptionLabel("ml:x", "x（lightgbm）")).toBe("ml:x（x（lightgbm））");
  });

  it("returns name when tip equals name", () => {
    expect(formatFactorOptionLabel("SMA_20", "SMA_20")).toBe("SMA_20");
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
});
