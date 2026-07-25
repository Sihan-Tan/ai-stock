/**
 * 因子勾选 → factor_rules 预填文档（与 Python `build_prefill_doc` 对齐）。
 */

/** 与 StrategyRuleBuilder Operand 结构兼容 */
export type PrefillOperand =
  | { kind: "factor"; factor: string; lag?: number }
  | { kind: "const"; const: number };

/** 与 StrategyRuleBuilder RuleCondition 结构兼容 */
export type PrefillCondition = {
  op: string;
  left: PrefillOperand;
  right: PrefillOperand;
};

/** 与 StrategyRuleBuilder RuleSide 结构兼容（扁平 all/any） */
export type PrefillSide = {
  combine: "all" | "any";
  conditions: PrefillCondition[];
};

/** 预填产出的规则文档（可交给 dumpFactorRulesYaml / setDoc） */
export type PrefillRuleDoc = {
  id: string;
  name: string;
  version: string;
  kind: "factor_rules";
  params: { position_pct: number; max_hold_bars: number };
  buy: PrefillSide;
  sell: PrefillSide;
};

/** 振荡类因子名白名单 token（忽略大小写，子串匹配） */
export const OSCILLATOR_TOKENS = [
  "RSI",
  "CCI",
  "WILLR",
  "WR",
  "STOCH",
  "KDJ",
  "MOM",
] as const;

/**
 * 因子名 → 可作策略 id 片段的安全字符串。
 * @param name 因子名
 */
function safeIdPart(name: string): string {
  const s = name.trim().replace(/[^A-Za-z0-9]+/g, "_");
  return s.replace(/^_+|_+$/g, "") || "factor";
}

/**
 * 因子名（忽略大小写）是否含振荡类 token。
 * @param name 因子名
 */
export function isOscillator(name: string): boolean {
  const upper = name.toUpperCase();
  return OSCILLATOR_TOKENS.some((tok) => upper.includes(tok));
}

/**
 * 名称是否以 SMA / EMA / MA 开头（忽略大小写）。
 * @param name 因子名
 */
export function isMaLike(name: string): boolean {
  const upper = name.toUpperCase();
  return upper.startsWith("SMA") || upper.startsWith("EMA") || upper.startsWith("MA");
}

/**
 * 构造因子 vs 常数比较条件。
 * @param factor 因子名
 * @param op 比较算子
 * @param constVal 常数
 */
function condCompare(factor: string, op: string, constVal: number): PrefillCondition {
  return {
    op,
    left: { kind: "factor", factor },
    right: { kind: "const", const: constVal },
  };
}

/**
 * 构造交叉条件。
 * @param left 左因子
 * @param op cross_up|cross_down
 * @param right 右因子
 */
function condCross(left: string, op: string, right: string): PrefillCondition {
  return {
    op,
    left: { kind: "factor", factor: left },
    right: { kind: "factor", factor: right },
  };
}

/**
 * 由勾选因子生成 factor_rules 草稿文档。
 *
 * - ml:* → buy gt 0.6 / sell lt 0.4
 * - 振荡类 → buy lt 30 / sell gt 70
 * - 均线类 → CLOSE cross_* factor
 * - 其它 TA → factor cross_* SMA_20
 *
 * @param factorNames 勾选的因子名列表
 */
export function buildPrefillRuleDoc(factorNames: string[]): PrefillRuleDoc {
  const names = factorNames
    .filter((n): n is string => typeof n === "string")
    .map((n) => n.trim())
    .filter(Boolean);
  const first = names[0] ?? "factor";
  const sid = `rule_from_${safeIdPart(first)}`;

  const buyConds: PrefillCondition[] = [];
  const sellConds: PrefillCondition[] = [];

  for (const name of names) {
    if (name.toLowerCase().startsWith("ml:")) {
      buyConds.push(condCompare(name, "gt", 0.6));
      sellConds.push(condCompare(name, "lt", 0.4));
    } else if (isOscillator(name)) {
      buyConds.push(condCompare(name, "lt", 30));
      sellConds.push(condCompare(name, "gt", 70));
    } else if (isMaLike(name)) {
      buyConds.push(condCross("CLOSE", "cross_up", name));
      sellConds.push(condCross("CLOSE", "cross_down", name));
    } else {
      buyConds.push(condCross(name, "cross_up", "SMA_20"));
      sellConds.push(condCross(name, "cross_down", "SMA_20"));
    }
  }

  return {
    id: sid,
    name: sid,
    kind: "factor_rules",
    version: "v0.1",
    params: { position_pct: 100, max_hold_bars: 0 },
    buy: { combine: "all", conditions: buyConds },
    sell: { combine: "any", conditions: sellConds },
  };
}

/**
 * 将 API / Python 风格操作数规范为 PrefillOperand（补全 kind）。
 * @param raw 原始操作数
 */
function normalizeOperand(raw: unknown): PrefillOperand {
  if (!raw || typeof raw !== "object") {
    return { kind: "factor", factor: "CLOSE" };
  }
  const o = raw as Record<string, unknown>;
  if (o.kind === "const" || "const" in o) {
    return { kind: "const", const: Number(o.const) };
  }
  const factor = typeof o.factor === "string" ? o.factor : "CLOSE";
  const op: PrefillOperand = { kind: "factor", factor };
  if (o.lag != null && Number.isFinite(Number(o.lag))) {
    const lag = Math.max(0, Math.floor(Number(o.lag)));
    if (lag > 0) (op as { lag?: number }).lag = lag;
  }
  return op;
}

/**
 * 将 API 返回的 yaml_body（对象或 YAML 字符串经外部 parse）规范为可 setDoc 的文档。
 * @param raw best.yaml_body
 */
export function normalizeRuleDocFromApi(raw: unknown): PrefillRuleDoc | null {
  if (!raw || typeof raw !== "object") return null;
  const d = raw as Record<string, unknown>;
  if (d.kind !== "factor_rules") return null;

  /**
   * @param sideRaw buy|sell 块
   * @param defaultCombine 缺省 combine
   */
  const normalizeSide = (
    sideRaw: unknown,
    defaultCombine: "all" | "any"
  ): PrefillSide => {
    const side = sideRaw && typeof sideRaw === "object" ? (sideRaw as Record<string, unknown>) : {};
    const combine =
      side.combine === "any" || side.combine === "all" ? side.combine : defaultCombine;
    const conditionsRaw = Array.isArray(side.conditions) ? side.conditions : [];
    const conditions: PrefillCondition[] = conditionsRaw
      .filter((c): c is Record<string, unknown> => !!c && typeof c === "object")
      .map((c) => ({
        op: typeof c.op === "string" ? c.op : "gt",
        left: normalizeOperand(c.left),
        right: normalizeOperand(c.right),
        ...(typeof c.pct === "number" ? { pct: c.pct } : {}),
        ...(typeof c.mult === "number" ? { mult: c.mult } : {}),
      }));
    return { combine, conditions };
  };

  const paramsRaw =
    d.params && typeof d.params === "object" ? (d.params as Record<string, unknown>) : {};
  const position_pct =
    paramsRaw.position_pct != null && Number.isFinite(Number(paramsRaw.position_pct))
      ? Number(paramsRaw.position_pct)
      : 100;
  const max_hold_bars =
    paramsRaw.max_hold_bars != null && Number.isFinite(Number(paramsRaw.max_hold_bars))
      ? Math.max(0, Math.floor(Number(paramsRaw.max_hold_bars)))
      : 0;

  return {
    id: typeof d.id === "string" ? d.id : "rule_new",
    name: typeof d.name === "string" ? d.name : "规则策略",
    version: typeof d.version === "string" ? d.version : "v0.1",
    kind: "factor_rules",
    params: { position_pct, max_hold_bars },
    buy: normalizeSide(d.buy, "all"),
    sell: normalizeSide(d.sell, "any"),
  };
}
