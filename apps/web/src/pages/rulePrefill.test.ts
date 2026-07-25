/** buildPrefillRuleDoc 与 Python build_prefill_doc 对齐的轻量单测。 */
import { describe, expect, it } from "vitest";
import {
  buildPrefillRuleDoc,
  isMaLike,
  isOscillator,
  normalizeRuleDocFromApi,
} from "./rulePrefill";
import { dumpFactorRulesYaml, parseFactorRulesYaml } from "./StrategyRuleBuilder";

describe("buildPrefillRuleDoc", () => {
  it("ml and rsi defaults", () => {
    const doc = buildPrefillRuleDoc(["ml:x", "RSI_14"]);
    expect(doc.kind).toBe("factor_rules");
    expect(doc.buy.combine).toBe("all");
    expect(doc.sell.combine).toBe("any");
    expect(doc.params.position_pct).toBe(100);
    expect(doc.params.max_hold_bars).toBe(0);
    expect(doc.id).toBe("rule_from_ml_x");
    expect(doc.name).toBe("rule_from_ml_x");
    expect(doc.version).toBe("v0.1");

    const buyOps = doc.buy.conditions.map((c) => c.op);
    expect(buyOps).toContain("gt");
    expect(buyOps).toContain("lt");

    const mlBuy = doc.buy.conditions.find((c) => c.left.kind === "factor" && c.left.factor === "ml:x");
    expect(mlBuy).toMatchObject({
      op: "gt",
      right: { kind: "const", const: 0.6 },
    });
    const rsiBuy = doc.buy.conditions.find(
      (c) => c.left.kind === "factor" && c.left.factor === "RSI_14"
    );
    expect(rsiBuy).toMatchObject({
      op: "lt",
      right: { kind: "const", const: 30 },
    });
    const rsiSell = doc.sell.conditions.find(
      (c) => c.left.kind === "factor" && c.left.factor === "RSI_14"
    );
    expect(rsiSell).toMatchObject({
      op: "gt",
      right: { kind: "const", const: 70 },
    });
  });

  it("ma-like uses CLOSE cross factor", () => {
    const doc = buildPrefillRuleDoc(["SMA_20"]);
    expect(doc.buy.conditions[0]).toMatchObject({
      op: "cross_up",
      left: { kind: "factor", factor: "CLOSE" },
      right: { kind: "factor", factor: "SMA_20" },
    });
    expect(doc.sell.conditions[0]).toMatchObject({
      op: "cross_down",
      left: { kind: "factor", factor: "CLOSE" },
      right: { kind: "factor", factor: "SMA_20" },
    });
  });

  it("other TA crosses SMA_20", () => {
    const doc = buildPrefillRuleDoc(["ATR_14"]);
    expect(doc.buy.conditions[0]).toMatchObject({
      op: "cross_up",
      left: { kind: "factor", factor: "ATR_14" },
      right: { kind: "factor", factor: "SMA_20" },
    });
  });

  it("produces doc dumpFactorRulesYaml accepts", () => {
    const doc = buildPrefillRuleDoc(["ml:demo", "RSI_14", "EMA_10"]);
    const yaml = dumpFactorRulesYaml(doc);
    expect(yaml).toContain("kind: factor_rules");
    expect(yaml).toContain("position_pct");
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed).not.toBeNull();
    expect(parsed?.buy.conditions.length).toBe(3);
    expect(parsed?.params?.position_pct).toBe(100);
  });
});

describe("isOscillator / isMaLike", () => {
  it("detects oscillator tokens", () => {
    expect(isOscillator("RSI_14")).toBe(true);
    expect(isOscillator("cci")).toBe(true);
    expect(isOscillator("ATR_14")).toBe(false);
  });

  it("detects ma-like prefixes", () => {
    expect(isMaLike("SMA_5")).toBe(true);
    expect(isMaLike("ema_20")).toBe(true);
    expect(isMaLike("MA10")).toBe(true);
    expect(isMaLike("RSI_14")).toBe(false);
  });
});

describe("normalizeRuleDocFromApi", () => {
  it("adds kind to Python-style operands", () => {
    const normalized = normalizeRuleDocFromApi({
      id: "r1",
      name: "r1",
      version: "v0.1",
      kind: "factor_rules",
      params: { position_pct: 50, max_hold_bars: 5 },
      buy: {
        combine: "all",
        conditions: [{ op: "gt", left: { factor: "ml:x" }, right: { const: 0.55 } }],
      },
      sell: {
        combine: "any",
        conditions: [{ op: "lt", left: { factor: "ml:x" }, right: { const: 0.4 } }],
      },
    });
    expect(normalized?.buy.conditions[0]?.left).toEqual({ kind: "factor", factor: "ml:x" });
    expect(normalized?.buy.conditions[0]?.right).toEqual({ kind: "const", const: 0.55 });
    expect(normalized?.params).toEqual({ position_pct: 50, max_hold_bars: 5 });
  });
});
