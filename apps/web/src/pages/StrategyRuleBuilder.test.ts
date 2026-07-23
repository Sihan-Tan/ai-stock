/** dumpFactorRulesYaml / parseFactorRulesYaml 轻量单测（纯函数）。 */
import { describe, expect, it } from "vitest";
import {
  dumpFactorRulesYaml,
  filterFactorOptions,
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

describe("filterFactorOptions", () => {
  const opts = [
    {
      value: "RSI_14",
      label: "RSI_14（相对强弱）",
      searchText: "rsi_14 rsi 相对强弱",
    },
    {
      value: "SMA_20",
      label: "SMA_20（简单移动平均）",
      searchText: "sma_20 sma 简单移动平均",
    },
    {
      value: "ml:foo",
      label: "ml:foo（模型）",
      searchText: "ml:foo foo 模型 lightgbm",
    },
  ];

  it("returns all when query empty", () => {
    expect(filterFactorOptions(opts, "  ")).toHaveLength(3);
  });

  it("matches name", () => {
    expect(filterFactorOptions(opts, "sma").map((o) => o.value)).toEqual(["SMA_20"]);
  });

  it("matches description in searchText", () => {
    expect(filterFactorOptions(opts, "相对强弱").map((o) => o.value)).toEqual(["RSI_14"]);
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

  it("dumps and parses sequence with within_bars", () => {
    const yaml = dumpFactorRulesYaml({
      id: "rule_seq",
      name: "跨日",
      version: "v1.0",
      kind: "factor_rules",
      buy: {
        combine: "sequence",
        within_bars: 5,
        conditions: [
          {
            op: "cross_up",
            left: { kind: "factor", factor: "SMA_5" },
            right: { kind: "factor", factor: "SMA_20" },
          },
          {
            op: "near_pct",
            left: { kind: "factor", factor: "CLOSE" },
            right: { kind: "factor", factor: "SMA_20" },
            pct: 3,
          },
        ],
      },
      sell: { combine: "within", within_bars: 10, conditions: [] },
    });
    expect(yaml).toContain("combine: sequence");
    expect(yaml).toContain("within_bars: 5");
    expect(yaml).toContain("combine: within");
    expect(yaml).toContain("within_bars: 10");
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed?.buy.combine).toBe("sequence");
    expect(parsed?.buy.within_bars).toBe(5);
    // 扁平 sequence 解析后升为 stages
    expect(parsed?.buy.stages?.length ?? 0).toBe(2);
    expect(parsed?.sell.combine).toBe("within");
    expect(parsed?.sell.within_bars).toBe(10);
  });

  it("dumps and parses lag and mult for volume compare", () => {
    const yaml = dumpFactorRulesYaml({
      id: "rule_vol",
      name: "放量",
      version: "v1.0",
      kind: "factor_rules",
      buy: {
        combine: "all",
        conditions: [
          {
            op: "gte",
            left: { kind: "factor", factor: "VOLUME" },
            right: { kind: "factor", factor: "VOLUME", lag: 1 },
            mult: 2,
          },
        ],
      },
      sell: { combine: "any", conditions: [] },
    });
    expect(yaml).toContain('factor: "VOLUME"');
    expect(yaml).toContain("lag: 1");
    expect(yaml).toContain("mult: 2");
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed?.buy.conditions[0]?.op).toBe("gte");
    expect(parsed?.buy.conditions[0]?.mult).toBe(2);
    expect(parsed?.buy.conditions[0]?.right).toEqual({
      kind: "factor",
      factor: "VOLUME",
      lag: 1,
    });
  });

  it("dumps and parses sequence stages", () => {
    const yaml = dumpFactorRulesYaml({
      id: "rule_st",
      name: "分阶段",
      version: "v1.0",
      kind: "factor_rules",
      buy: {
        combine: "sequence",
        within_bars: 5,
        conditions: [],
        stages: [
          {
            combine: "all",
            conditions: [
              {
                op: "gt",
                left: { kind: "factor", factor: "VOLUME" },
                right: { kind: "const", const: 0 },
              },
              {
                op: "gt",
                left: { kind: "factor", factor: "CLOSE" },
                right: { kind: "const", const: 9 },
              },
            ],
          },
          {
            combine: "all",
            within_bars: 3,
            conditions: [
              {
                op: "lt",
                left: { kind: "factor", factor: "CLOSE" },
                right: { kind: "const", const: 9 },
              },
            ],
          },
        ],
      },
      sell: { combine: "any", conditions: [] },
    });
    expect(yaml).toContain("stages:");
    expect(yaml).toContain("within_bars: 3");
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed?.buy.combine).toBe("sequence");
    expect(parsed?.buy.stages).toHaveLength(2);
    expect(parsed?.buy.stages?.[0]?.conditions).toHaveLength(2);
    expect(parsed?.buy.stages?.[1]?.within_bars).toBe(3);
    expect(parsed?.buy.stages?.[1]?.conditions[0]?.op).toBe("lt");
  });
});
