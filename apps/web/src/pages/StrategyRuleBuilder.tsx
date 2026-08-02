import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { FactorMeta } from "../factors/types";
import { DateRangePresetSelect } from "../ui/DateRangePresetSelect";
import {
  defaultDateRangeValue,
  type DateRangeValue,
  validateDateRange,
} from "../ui/dateRange";
import {
  buildPrefillRuleDoc,
  normalizeRuleDocFromApi,
  type PrefillRuleDoc,
} from "./rulePrefill";
import type { PageLogProps } from "./types";

type Operand =
  | { kind: "factor"; factor: string; /** 滞后天数，默认 0 */ lag?: number }
  | { kind: "const"; const: number };

type RuleCondition = {
  op: string;
  left: Operand;
  right: Operand;
  /** near_pct 专用：±百分比，默认 3 */
  pct?: number;
  /** 比较类：右端倍数，默认 1（left 与 right×mult 比较） */
  mult?: number;
};

type RuleCombine = "all" | "any" | "sequence" | "within";

/** sequence 下的一个阶段（阶段内同日 all/any）。 */
type RuleStage = {
  combine: "all" | "any";
  /** 距上一阶段完成日的最大间隔；首段忽略 */
  within_bars?: number;
  conditions: RuleCondition[];
};

type RuleSide = {
  combine: RuleCombine;
  /** sequence 默认段间隔 / within 窗口（交易日），默认 5 */
  within_bars?: number;
  conditions: RuleCondition[];
  /** sequence 分阶段；优先于扁平 conditions */
  stages?: RuleStage[];
};

/** 规则顶层 params（仓位% / 最长持仓 bars）。 */
export type RuleParams = {
  position_pct?: number;
  max_hold_bars?: number;
};

/** 规则构建器文档（含可选 params，与 dump/parse 对齐）。 */
export type RuleDoc = {
  id: string;
  name: string;
  version: string;
  kind: "factor_rules";
  params?: RuleParams;
  buy: RuleSide;
  sell: RuleSide;
};

/** 寻优 API 成功响应。 */
type OptimizeRulesResult = {
  best?: {
    yaml_body?: unknown;
    metrics?: {
      total_return?: number;
      max_drawdown?: number;
      trades?: number;
      sharpe?: number | null;
    };
    buy_threshold?: number | null;
    sell_threshold?: number | null;
    position_pct?: number;
    max_hold_bars?: number;
  };
  tried?: number;
  skipped?: number;
};

const OPS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "eq", label: "=" },
  { value: "cross_up", label: "上穿" },
  { value: "cross_down", label: "下穿" },
  { value: "near_pct", label: "贴近(±%)" },
];

const controlClass =
  "rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 py-1.5 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 默认空条件。
 */
function emptyCondition(): RuleCondition {
  return {
    op: "near_pct",
    left: { kind: "factor", factor: "CLOSE" },
    right: { kind: "factor", factor: "SMA_20" },
    pct: 3,
  };
}

/**
 * 默认空阶段。
 * @param withinBars 距上一段间隔（首段可不传）
 */
function emptyStage(withinBars?: number): RuleStage {
  return {
    combine: "all",
    within_bars: withinBars,
    conditions: [emptyCondition()],
  };
}

/**
 * 序列化单条条件。
 * @param cond 条件
 * @param itemIndent 列表项缩进（含 `- ` 前空格）
 * @param fieldIndent 字段缩进
 */
function dumpConditionLines(
  cond: RuleCondition,
  itemIndent: string,
  fieldIndent: string
): string[] {
  const lines: string[] = [`${itemIndent}- op: ${cond.op}`];
  lines.push(`${fieldIndent}left:`);
  lines.push(dumpOperand(cond.left, `${fieldIndent}  `));
  lines.push(`${fieldIndent}right:`);
  lines.push(dumpOperand(cond.right, `${fieldIndent}  `));
  if (cond.op === "near_pct") {
    const pct = Number.isFinite(cond.pct) ? Number(cond.pct) : 3;
    lines.push(`${fieldIndent}pct: ${pct}`);
  } else if (["gt", "gte", "lt", "lte", "eq"].includes(cond.op)) {
    const mult = Number.isFinite(cond.mult) ? Number(cond.mult) : 1;
    if (mult !== 1) lines.push(`${fieldIndent}mult: ${mult}`);
  }
  return lines;
}

/**
 * 从条件文本块解析一条条件。
 * @param raw 条件片段
 */
function parseConditionBlock(raw: string): RuleCondition {
  const opM = raw.match(/(?:^|\n)\s*op:\s*([a-z_]+)/) || raw.match(/^op:\s*([a-z_]+)/m);
  const left = parseOperand(raw, "left") ?? { kind: "factor" as const, factor: "SMA_5" };
  const right = parseOperand(raw, "right") ?? { kind: "factor" as const, factor: "SMA_20" };
  const op = opM?.[1] || "gt";
  const pctM = raw.match(/(?:^|\n)\s*pct:\s*([-\d.]+)/);
  const multM = raw.match(/(?:^|\n)\s*mult:\s*([-\d.]+)/);
  const cond: RuleCondition = { op, left, right };
  if (op === "near_pct") {
    cond.pct = pctM ? Number(pctM[1]) : 3;
  } else if (["gt", "gte", "lt", "lte", "eq"].includes(op) && multM) {
    cond.mult = Number(multM[1]);
  }
  return cond;
}

/**
 * 默认规则文档。
 */
function defaultDoc(): RuleDoc {
  return {
    id: "rule_new",
    name: "新规则策略",
    version: "v1.0",
    kind: "factor_rules",
    params: { position_pct: 100, max_hold_bars: 0 },
    buy: {
      combine: "all",
      conditions: [
        {
          op: "cross_up",
          left: { kind: "factor", factor: "SMA_5" },
          right: { kind: "factor", factor: "SMA_20" },
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
  };
}

/**
 * 操作数序列化为 YAML 片段。
 * @param op 操作数
 * @param indent 缩进空格
 */
function dumpOperand(op: Operand, indent: string): string {
  if (op.kind === "const") {
    return `${indent}const: ${Number.isFinite(op.const) ? op.const : 0}`;
  }
  const lines = [`${indent}factor: ${JSON.stringify(op.factor || "SMA_5")}`];
  const lag = Number.isFinite(op.lag) ? Math.max(0, Math.floor(Number(op.lag))) : 0;
  if (lag > 0) {
    lines.push(`${indent}lag: ${lag}`);
  }
  return lines.join("\n");
}

/**
 * 将规则文档序列化为 YAML（手写，避免依赖 js-yaml）。
 * @param doc 规则文档（含 PrefillRuleDoc）
 */
export function dumpFactorRulesYaml(doc: RuleDoc | PrefillRuleDoc): string {
  const lines: string[] = [
    `id: ${JSON.stringify(doc.id.trim() || "rule_new")}`,
    `name: ${JSON.stringify(doc.name.trim() || "规则策略")}`,
    `version: ${JSON.stringify(doc.version.trim() || "v1.0")}`,
    `kind: factor_rules`,
  ];

  if (doc.params && typeof doc.params === "object") {
    lines.push(`params:`);
    if (doc.params.position_pct != null && Number.isFinite(Number(doc.params.position_pct))) {
      lines.push(`  position_pct: ${Number(doc.params.position_pct)}`);
    }
    if (doc.params.max_hold_bars != null && Number.isFinite(Number(doc.params.max_hold_bars))) {
      lines.push(`  max_hold_bars: ${Math.max(0, Math.floor(Number(doc.params.max_hold_bars)))}`);
    }
  }

  /**
   * @param key buy|sell
   * @param side 条件组
   */
  const dumpSide = (key: "buy" | "sell", side: RuleSide) => {
    lines.push(`${key}:`);
    const combine =
      side.combine === "any"
        ? "any"
        : side.combine === "sequence"
          ? "sequence"
          : side.combine === "within"
            ? "within"
            : "all";
    lines.push(`  combine: ${combine}`);
    if (combine === "sequence" || combine === "within") {
      const n = Number.isFinite(side.within_bars) ? Number(side.within_bars) : 5;
      lines.push(`  within_bars: ${Math.max(0, Math.floor(n))}`);
    }
    if (combine === "sequence" && side.stages && side.stages.length > 0) {
      lines.push(`  stages:`);
      side.stages.forEach((stage, stageIndex) => {
        lines.push(`    - combine: ${stage.combine === "any" ? "any" : "all"}`);
        if (stageIndex > 0) {
          const wb = Number.isFinite(stage.within_bars)
            ? Number(stage.within_bars)
            : Number.isFinite(side.within_bars)
              ? Number(side.within_bars)
              : 5;
          lines.push(`      within_bars: ${Math.max(0, Math.floor(wb))}`);
        }
        lines.push(`      conditions:`);
        if (stage.conditions.length === 0) {
          lines.push(`        []`);
          return;
        }
        for (const cond of stage.conditions) {
          lines.push(...dumpConditionLines(cond, "        ", "          "));
        }
      });
      return;
    }
    lines.push(`  conditions:`);
    if (side.conditions.length === 0) {
      lines.push(`    []`);
      return;
    }
    for (const cond of side.conditions) {
      lines.push(...dumpConditionLines(cond, "    ", "      "));
    }
  };

  dumpSide("buy", doc.buy);
  dumpSide("sell", doc.sell);
  return `${lines.join("\n")}\n`;
}

/**
 * 从 YAML 文本尽力解析规则文档（兼容构建器产出与 PyYAML safe_dump）。
 * @param text YAML
 */
export function parseFactorRulesYaml(text: string): RuleDoc | null {
  if (!/kind:\s*factor_rules/.test(text)) return null;
  const base = defaultDoc();
  const idM = text.match(/^id:\s*(.+)$/m);
  const nameM = text.match(/^name:\s*(.+)$/m);
  const verM = text.match(/^version:\s*(.+)$/m);
  if (idM) base.id = unquote(idM[1]);
  if (nameM) base.name = unquote(nameM[1]);
  if (verM) base.version = unquote(verM[1]);

  const paramsBlock = text.match(
    /(?:^|\r?\n)params:\r?\n((?:[ \t]+[^\r\n]*\r?\n?)*)/
  )?.[1];
  if (paramsBlock) {
    const posM = paramsBlock.match(/position_pct:\s*([-\d.]+)/);
    const holdM = paramsBlock.match(/max_hold_bars:\s*([-\d.]+)/);
    base.params = {
      ...(posM && Number.isFinite(Number(posM[1]))
        ? { position_pct: Number(posM[1]) }
        : {}),
      ...(holdM && Number.isFinite(Number(holdM[1]))
        ? { max_hold_bars: Math.max(0, Math.floor(Number(holdM[1]))) }
        : {}),
    };
  }

  /**
   * @param section buy|sell
   */
  const parseSide = (section: "buy" | "sell"): RuleSide => {
    const side: RuleSide =
      section === "buy"
        ? { ...base.buy, conditions: [] as RuleCondition[], stages: undefined }
        : { ...base.sell, conditions: [] as RuleCondition[], stages: undefined };
    const blockRe = new RegExp(
      `(?:^|\\r?\\n)${section}:\\r?\\n([\\s\\S]*?)(?=\\r?\\n(?:buy|sell|id|name|version|kind|params):|\\s*$)`
    );
    const block = text.match(blockRe)?.[1] ?? "";
    const combineM = block.match(/combine:\s*(all|any|sequence|within)/);
    if (combineM) side.combine = combineM[1] as RuleCombine;
    const wbM = block.match(/(?:^|\r?\n)  within_bars:\s*(\d+)/);
    if (wbM) side.within_bars = Number(wbM[1]);
    else if (side.combine === "sequence" || side.combine === "within") side.within_bars = 5;

    if (side.combine === "sequence" && /stages:/.test(block)) {
      side.stages = parseStagesYaml(block);
      side.conditions = [];
      return side;
    }

    if (/conditions:\s*\[\s*\]/.test(block)) {
      return side;
    }
    const condBlocks = block.split(/\n\s*-\s+/).slice(1);
    for (const raw of condBlocks) {
      // 跳过 stages 误切（旧路径不应含 stages）
      if (/^\s*combine:\s*(all|any)/.test(raw) && /conditions:/.test(raw) && !/\bop:/.test(raw)) {
        continue;
      }
      side.conditions.push(parseConditionBlock(raw));
    }
    // 扁平 sequence → 升为 stages，便于 UI
    if (side.combine === "sequence" && side.conditions.length > 0 && !side.stages?.length) {
      const defWb = side.within_bars ?? 5;
      side.stages = side.conditions.map((c, i) => ({
        combine: "all" as const,
        within_bars: i > 0 ? defWb : undefined,
        conditions: [c],
      }));
      side.conditions = [];
    }
    return side;
  };

  base.buy = parseSide("buy");
  base.sell = parseSide("sell");
  return base;
}

/**
 * 解析条件中的 left/right 操作数（支持多行与 {factor|const: ...} 流式写法）。
 * @param raw 单条条件文本
 * @param side left|right
 */
function parseOperand(raw: string, side: "left" | "right"): Operand | null {
  const flowFactor = raw.match(
    new RegExp(`${side}:\\s*\\{\\s*factor:\\s*([^,}]+)(?:,\\s*lag:\\s*(\\d+))?\\s*\\}`)
  );
  if (flowFactor) {
    const op: Operand = { kind: "factor", factor: unquote(flowFactor[1]) };
    if (flowFactor[2]) op.lag = Number(flowFactor[2]);
    return op;
  }
  const flowConst = raw.match(
    new RegExp(`${side}:\\s*\\{\\s*const:\\s*([-\\d.]+)\\s*\\}`)
  );
  if (flowConst) {
    return { kind: "const", const: Number(flowConst[1]) };
  }
  const block = raw.match(
    new RegExp(`${side}:\\s*\\n((?:\\s{2,}[^\\n]+\\n?)*)`)
  );
  if (block) {
    const body = block[1];
    const factorM = body.match(/^\s*factor:\s*(.+)$/m);
    if (factorM) {
      const op: Operand = { kind: "factor", factor: unquote(factorM[1]) };
      const lagM = body.match(/^\s*lag:\s*(\d+)\s*$/m);
      if (lagM) op.lag = Number(lagM[1]);
      return op;
    }
    const constM = body.match(/^\s*const:\s*([-\\d.]+)\s*$/m);
    if (constM) {
      return { kind: "const", const: Number(constM[1]) };
    }
  }
  const factorM = raw.match(new RegExp(`${side}:\\s*\\n\\s+factor:\\s*(.+)`));
  if (factorM) {
    return { kind: "factor", factor: unquote(factorM[1]) };
  }
  const constM = raw.match(new RegExp(`${side}:\\s*\\n\\s+const:\\s*([-\\d.]+)`));
  if (constM) {
    return { kind: "const", const: Number(constM[1]) };
  }
  return null;
}

/**
 * 从 buy/sell 块中解析 stages 列表（行扫描，避免条件项误切）。
 * @param block YAML 侧块文本
 */
function parseStagesYaml(block: string): RuleStage[] {
  const lines = block.split(/\r?\n/);
  let i = lines.findIndex((l) => /^\s*stages:\s*$/.test(l));
  if (i < 0) return [];
  i += 1;
  const stages: RuleStage[] = [];
  let cur: RuleStage | null = null;
  let inConditions = false;
  let condBuf: string[] = [];

  const flushCond = () => {
    if (condBuf.length && cur) {
      cur.conditions.push(parseConditionBlock(condBuf.join("\n")));
      condBuf = [];
    }
  };

  for (; i < lines.length; i++) {
    const line = lines[i];
    if (/^(buy|sell|id|name|version|kind|params):/.test(line)) break;

    const stageStart = line.match(/^\s{4}-\s+combine:\s*(all|any)\s*$/);
    if (stageStart) {
      flushCond();
      if (cur) stages.push(cur);
      cur = { combine: stageStart[1] === "any" ? "any" : "all", conditions: [] };
      inConditions = false;
      continue;
    }
    if (!cur) continue;

    const wb = line.match(/^\s+within_bars:\s*(\d+)\s*$/);
    if (wb) {
      cur.within_bars = Number(wb[1]);
      continue;
    }
    if (/^\s+conditions:\s*\[\s*\]\s*$/.test(line)) {
      inConditions = true;
      continue;
    }
    if (/^\s+conditions:\s*$/.test(line)) {
      inConditions = true;
      continue;
    }
    if (inConditions) {
      if (/^\s{8}-\s+/.test(line)) {
        flushCond();
        condBuf = [line.replace(/^\s{8}-\s+/, "")];
      } else if (condBuf.length > 0) {
        condBuf.push(line);
      }
    }
  }
  flushCond();
  if (cur) stages.push(cur);
  return stages.filter((s) => s.conditions.length > 0);
}

/**
 * 去掉 YAML 标量引号。
 * @param raw 原始片段
 */
function unquote(raw: string): string {
  const s = raw.trim();
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1);
  }
  return s;
}

/**
 * 规则构建器因子下拉文案：因子名（短中文 label）。
 * @param name 因子名
 * @param label 短标签
 * @param _description 详述（仅供调用方兼容；不用于选项主文案）
 */
export function formatFactorOptionLabel(
  name: string,
  label: string,
  _description?: string
): string {
  const tip = (label || "").trim();
  if (!tip || tip === name) return name;
  return `${name}（${tip}）`;
}

/** 规则条件因子下拉选项。 */
export type FactorOption = {
  value: string;
  label: string;
  /** 小写检索串：name + label + description */
  searchText: string;
};

/**
 * 按关键字过滤因子选项（name / label / description 包含匹配）。
 * @param options 全量选项
 * @param query 用户输入
 */
export function filterFactorOptions(options: FactorOption[], query: string): FactorOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  return options.filter(
    (o) =>
      o.searchText.includes(q) ||
      o.value.toLowerCase().includes(q) ||
      o.label.toLowerCase().includes(q)
  );
}

/**
 * 策略规则构建器：因子比较 / 交叉 → factor_rules YAML。
 * @param props 页面日志
 */
export default function StrategyRuleBuilder({ setLog }: PageLogProps) {
  const navigate = useNavigate();
  const { strategyId } = useParams();
  const [searchParams] = useSearchParams();
  const isNew = !strategyId;
  const [doc, setDoc] = useState<RuleDoc>(() => defaultDoc());
  const [factors, setFactors] = useState<FactorMeta[]>([]);
  const [factorsReady, setFactorsReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const [optOpen, setOptOpen] = useState(false);
  const [optSymbol, setOptSymbol] = useState("");
  const [optRange, setOptRange] = useState<DateRangeValue>(() => defaultDateRangeValue());
  const [optBusy, setOptBusy] = useState(false);
  const [optError, setOptError] = useState<string | null>(null);
  const prefillAppliedRef = useRef(false);

  const factorOptions = useMemo(
    () =>
      factors
        .filter((f) => f.enabled)
        .map((f) => ({
          value: f.name,
          label: formatFactorOptionLabel(f.name, f.label, f.description),
          searchText: `${f.name} ${f.label || ""} ${f.description || ""}`.toLowerCase(),
        })),
    [factors]
  );

  useEffect(() => {
    void api<{ factors: FactorMeta[] }>("/api/factors")
      .then((res) => setFactors(res.factors ?? []))
      .catch((error) => setLog(String(error)))
      .finally(() => setFactorsReady(true));
  }, [setLog]);

  useEffect(() => {
    if (!isNew || !factorsReady || prefillAppliedRef.current) return;
    if (searchParams.get("from") !== "factors") return;
    const names = (searchParams.get("factors") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!names.length) return;
    prefillAppliedRef.current = true;
    setDoc(buildPrefillRuleDoc(names));
    setLog(`已从因子预填规则：${names.join(", ")}`);
  }, [isNew, factorsReady, searchParams, setLog]);

  useEffect(() => {
    if (isNew || !strategyId) return;
    setLoading(true);
    void api<{ text?: string; language?: string }>(
      `/api/strategies/${encodeURIComponent(strategyId)}/source`
    )
      .then((src) => {
        const parsed = parseFactorRulesYaml(src.text || "");
        if (parsed) setDoc(parsed);
        else setLog("该策略不是 factor_rules 格式，已显示默认模板");
      })
      .catch((error) => setLog(String(error)))
      .finally(() => setLoading(false));
  }, [isNew, strategyId, setLog]);

  /**
   * 更新一侧规则。
   * @param side buy|sell
   * @param next 下一状态
   */
  const patchSide = useCallback((side: "buy" | "sell", next: RuleSide) => {
    setDoc((prev) => ({ ...prev, [side]: next }));
  }, []);

  /**
   * 保存为 YAML 策略。
   */
  const save = async () => {
    if (!doc.id.trim()) {
      setLog("请填写策略 ID");
      return;
    }
    if (doc.buy.conditions.length === 0 && doc.sell.conditions.length === 0) {
      const buyOk =
        doc.buy.combine === "sequence" &&
        (doc.buy.stages || []).some((s) => s.conditions.length > 0);
      const sellOk =
        doc.sell.combine === "sequence" &&
        (doc.sell.stages || []).some((s) => s.conditions.length > 0);
      if (!buyOk && !sellOk) {
        setLog("买卖条件不能都为空");
        return;
      }
    }
    setBusy(true);
    try {
      const yaml_body = dumpFactorRulesYaml(doc);
      const saved = await api<{ id: string }>("/api/strategies/from-yaml", {
        method: "POST",
        body: JSON.stringify({ yaml_body }),
      });
      setLog(`已保存规则策略 ${saved.id}`);
      navigate(`/strategies/${encodeURIComponent(saved.id)}/edit/rules`);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 提交阈值寻优。
   */
  const runOptimize = async () => {
    const symbol = optSymbol.trim();
    if (!symbol) {
      setOptError("请填写标的代码");
      return;
    }
    const rangeError = validateDateRange(optRange.start, optRange.end);
    if (rangeError) {
      setOptError(rangeError);
      return;
    }
    setOptBusy(true);
    setOptError(null);
    try {
      const res = await api<OptimizeRulesResult>("/api/strategies/optimize-rules", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          start: optRange.start,
          end: optRange.end,
          yaml_body: doc,
        }),
      });
      const body = res.best?.yaml_body;
      if (typeof body === "string") {
        const parsed = parseFactorRulesYaml(body);
        if (parsed) setDoc(parsed);
        else throw new Error("寻优结果 YAML 无法解析");
      } else {
        const normalized = normalizeRuleDocFromApi(body);
        if (normalized) setDoc(normalized);
        else if (body && typeof body === "object" && (body as RuleDoc).kind === "factor_rules") {
          setDoc(body as RuleDoc);
        } else {
          throw new Error("寻优结果缺少有效 yaml_body");
        }
      }
      const m = res.best?.metrics;
      const ret = m?.total_return;
      const dd = m?.max_drawdown;
      const trades = m?.trades;
      setLog(
        `寻优完成 tried=${res.tried ?? "?"} skipped=${res.skipped ?? 0}` +
          ` return=${ret != null ? Number(ret).toFixed(4) : "—"}` +
          ` dd=${dd != null ? Number(dd).toFixed(4) : "—"}` +
          ` trades=${trades ?? "—"}` +
          (res.best?.position_pct != null ? ` pos%=${res.best.position_pct}` : "") +
          (res.best?.max_hold_bars != null ? ` hold=${res.best.max_hold_bars}` : "")
      );
      setOptOpen(false);
    } catch (error) {
      setOptError(String(error));
      setLog(String(error));
    } finally {
      setOptBusy(false);
    }
  };

  if (loading) {
    return (
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="p-8 text-sm text-[var(--desk-mist)]">加载规则…</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">
              {isNew ? "新建规则策略" : "编辑规则策略"}
            </CardTitle>
            <Chip size="sm" variant="soft">
              factor_rules
            </Chip>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button size="sm" variant="secondary" onPress={() => navigate("/strategies")}>
              返回列表
            </Button>
            <Button
              size="sm"
              variant="secondary"
              isDisabled={busy || optBusy}
              onPress={() => {
                setOptError(null);
                setOptOpen(true);
              }}
            >
              阈值寻优
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy || optBusy} onPress={() => void save()}>
              {busy ? "保存中…" : "保存"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
              策略 ID
              <input
                className={`${controlClass} block w-full font-mono`}
                value={doc.id}
                onChange={(e) => setDoc((p) => ({ ...p, id: e.target.value }))}
              />
            </label>
            <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
              名称
              <input
                className={`${controlClass} block w-full`}
                value={doc.name}
                onChange={(e) => setDoc((p) => ({ ...p, name: e.target.value }))}
              />
            </label>
            <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
              版本
              <input
                className={`${controlClass} block w-full font-mono`}
                value={doc.version}
                onChange={(e) => setDoc((p) => ({ ...p, version: e.target.value }))}
              />
            </label>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
              仓位 %（params.position_pct）
              <input
                type="number"
                min={1}
                max={100}
                step={1}
                className={`${controlClass} block w-full font-mono`}
                value={doc.params?.position_pct ?? ""}
                onChange={(e) => {
                  const v = e.target.value === "" ? undefined : Number(e.target.value);
                  setDoc((p) => ({
                    ...p,
                    params: {
                      ...p.params,
                      position_pct: v != null && Number.isFinite(v) ? v : undefined,
                    },
                  }));
                }}
              />
            </label>
            <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
              最长持仓 bars（params.max_hold_bars）
              <input
                type="number"
                min={0}
                step={1}
                className={`${controlClass} block w-full font-mono`}
                value={doc.params?.max_hold_bars ?? ""}
                onChange={(e) => {
                  const v = e.target.value === "" ? undefined : Number(e.target.value);
                  setDoc((p) => ({
                    ...p,
                    params: {
                      ...p.params,
                      max_hold_bars:
                        v != null && Number.isFinite(v) ? Math.max(0, Math.floor(v)) : undefined,
                    },
                  }));
                }}
              />
            </label>
          </div>
          <p className="text-xs text-[var(--desk-mist)]">
            买/卖各一组条件；同 bar 同时满足时卖优先。保存后可在回测页选用。
          </p>
          <div className="flex flex-col gap-4">
            <RuleSideEditor
              title="买入条件"
              side={doc.buy}
              factorOptions={factorOptions}
              onChange={(next) => patchSide("buy", next)}
            />
            <RuleSideEditor
              title="卖出条件"
              side={doc.sell}
              factorOptions={factorOptions}
              onChange={(next) => patchSide("sell", next)}
            />
          </div>
        </CardContent>
      </Card>

      {optOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 cursor-default bg-black/50"
            aria-label="关闭阈值寻优"
            onClick={() => !optBusy && setOptOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="阈值寻优"
            className="relative z-10 w-full max-w-md rounded-xl border border-[var(--desk-line)] bg-[var(--desk-panel)] shadow-2xl"
          >
            <div className="flex items-start justify-between gap-3 border-b border-[var(--desk-line)] px-5 py-4">
              <div>
                <h2 className="text-base font-medium text-[var(--desk-text)]">阈值寻优</h2>
                <p className="mt-1 text-xs text-[var(--desk-mist)]">
                  网格回测买卖阈值 / 仓位% / 最长持仓，写回当前规则
                </p>
              </div>
              <Button size="sm" variant="ghost" isDisabled={optBusy} onPress={() => setOptOpen(false)}>
                关闭
              </Button>
            </div>
            <div className="space-y-4 px-5 py-4">
              <label className="block space-y-1 text-xs text-[var(--desk-mist)]">
                标的
                <input
                  className={`${controlClass} block w-full font-mono`}
                  placeholder="如 600519.SH"
                  value={optSymbol}
                  onChange={(e) => setOptSymbol(e.target.value)}
                  disabled={optBusy}
                />
              </label>
              <div className="space-y-1">
                <div className="text-xs text-[var(--desk-mist)]">回测区间</div>
                <DateRangePresetSelect
                  value={optRange}
                  onChange={setOptRange}
                  aria-label="寻优时间区间"
                />
              </div>
              {optError ? <p className="text-sm text-red-400">{optError}</p> : null}
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="secondary" isDisabled={optBusy} onPress={() => setOptOpen(false)}>
                  取消
                </Button>
                <Button size="sm" variant="primary" isDisabled={optBusy} onPress={() => void runOptimize()}>
                  {optBusy ? "寻优中…" : "开始寻优"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * 单侧（买/卖）条件编辑。
 * @param props 标题与条件组
 */
function RuleSideEditor({
  title,
  side,
  factorOptions,
  onChange,
}: {
  title: string;
  side: RuleSide;
  factorOptions: FactorOption[];
  onChange: (next: RuleSide) => void;
}) {
  const isSequence = side.combine === "sequence";
  const stages = side.stages?.length ? side.stages : [];

  /**
   * 切换组合方式时在扁平条件与 stages 间迁移。
   * @param value 新 combine
   */
  const onCombineChange = (value: RuleCombine) => {
    const next: RuleSide = { ...side, combine: value };
    if (value === "sequence") {
      next.within_bars = next.within_bars ?? 5;
      if (!next.stages?.length) {
        next.stages =
          next.conditions.length > 0
            ? next.conditions.map((c, i) => ({
                combine: "all" as const,
                within_bars: i > 0 ? next.within_bars : undefined,
                conditions: [c],
              }))
            : [emptyStage()];
        next.conditions = [];
      }
    } else if (side.combine === "sequence" && side.stages?.length) {
      next.conditions = side.stages.flatMap((s) => s.conditions);
      next.stages = undefined;
      if (value === "within") next.within_bars = next.within_bars ?? 5;
    } else if (value === "within" && next.within_bars === undefined) {
      next.within_bars = 5;
    }
    onChange(next);
  };

  /**
   * 更新某一阶段。
   * @param stageIndex 阶段下标
   * @param stage 新阶段
   */
  const patchStage = (stageIndex: number, stage: RuleStage) => {
    const nextStages = [...stages];
    nextStages[stageIndex] = stage;
    onChange({ ...side, stages: nextStages, conditions: [] });
  };

  return (
    <section className="space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/30 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-[var(--desk-text)]">{title}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className={controlClass}
            value={side.combine}
            onChange={(e) => onCombineChange(e.target.value as RuleCombine)}
            aria-label={`${title}组合方式`}
          >
            <option value="all">全部满足 (AND)</option>
            <option value="any">任一满足 (OR)</option>
            <option value="sequence">有序间隔（分阶段）</option>
            <option value="within">近N日均曾成立</option>
          </select>
          {side.combine === "within" ? (
            <label className="flex items-center gap-1 text-xs text-[var(--desk-mist)]">
              近窗（交易日）
              <input
                type="number"
                min={0}
                step={1}
                className={`${controlClass} w-20 font-mono`}
                value={Number.isFinite(side.within_bars) ? side.within_bars : 5}
                onChange={(e) =>
                  onChange({
                    ...side,
                    within_bars: Math.max(0, Math.floor(Number(e.target.value))),
                  })
                }
                aria-label="近窗交易日"
              />
            </label>
          ) : null}
          {isSequence ? (
            <label className="flex items-center gap-1 text-xs text-[var(--desk-mist)]">
              默认段间隔≤
              <input
                type="number"
                min={0}
                step={1}
                className={`${controlClass} w-20 font-mono`}
                value={Number.isFinite(side.within_bars) ? side.within_bars : 5}
                onChange={(e) =>
                  onChange({
                    ...side,
                    within_bars: Math.max(0, Math.floor(Number(e.target.value))),
                  })
                }
                aria-label="默认段间隔"
              />
            </label>
          ) : null}
        </div>
      </div>

      {isSequence ? (
        <div className="space-y-3">
          {stages.map((stage, stageIndex) => (
            <div
              key={stageIndex}
              className="space-y-2 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)]/50 p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium text-[var(--desk-text)]">
                    阶段 {stageIndex + 1}
                  </span>
                  <select
                    className={controlClass}
                    value={stage.combine}
                    onChange={(e) =>
                      patchStage(stageIndex, {
                        ...stage,
                        combine: e.target.value === "any" ? "any" : "all",
                      })
                    }
                    aria-label={`阶段${stageIndex + 1}组内组合`}
                  >
                    <option value="all">同日全部</option>
                    <option value="any">同日任一</option>
                  </select>
                  {stageIndex > 0 ? (
                    <label className="flex items-center gap-1 text-xs text-[var(--desk-mist)]">
                      距上阶段≤
                      <input
                        type="number"
                        min={0}
                        step={1}
                        className={`${controlClass} w-16 font-mono`}
                        value={
                          Number.isFinite(stage.within_bars)
                            ? stage.within_bars
                            : side.within_bars ?? 5
                        }
                        onChange={(e) =>
                          patchStage(stageIndex, {
                            ...stage,
                            within_bars: Math.max(0, Math.floor(Number(e.target.value))),
                          })
                        }
                        aria-label={`阶段${stageIndex + 1}间隔`}
                      />
                      日
                    </label>
                  ) : (
                    <span className="text-xs text-[var(--desk-mist)]">（起点，同日满足组内条件）</span>
                  )}
                </div>
                {stages.length > 1 ? (
                  <button
                    type="button"
                    className="text-xs text-[var(--desk-mist)] hover:text-[var(--danger)]"
                    onClick={() => {
                      const nextStages = stages.filter((_, i) => i !== stageIndex);
                      onChange({ ...side, stages: nextStages, conditions: [] });
                    }}
                  >
                    删除阶段
                  </button>
                ) : null}
              </div>
              <ConditionList
                conditions={stage.conditions}
                factorOptions={factorOptions}
                onChange={(conditions) => patchStage(stageIndex, { ...stage, conditions })}
              />
            </div>
          ))}
          <Button
            size="sm"
            variant="secondary"
            onPress={() =>
              onChange({
                ...side,
                stages: [...stages, emptyStage(side.within_bars ?? 5)],
                conditions: [],
              })
            }
          >
            添加阶段
          </Button>
        </div>
      ) : (
        <ConditionList
          conditions={side.conditions}
          factorOptions={factorOptions}
          onChange={(conditions) => onChange({ ...side, conditions })}
        />
      )}
    </section>
  );
}

/**
 * 条件列表（扁平或阶段内）。
 * @param props 条件与回调
 */
function ConditionList({
  conditions,
  factorOptions,
  onChange,
}: {
  conditions: RuleCondition[];
  factorOptions: FactorOption[];
  onChange: (next: RuleCondition[]) => void;
}) {
  return (
    <>
      <ul className="space-y-2">
        {conditions.map((cond, index) => (
          <li
            key={index}
            className="space-y-2 rounded-md border border-[var(--desk-line)] bg-[var(--desk-panel)]/40 p-2.5"
          >
            <div className="flex flex-wrap items-center gap-2">
              <OperandEditor
                value={cond.left}
                factorOptions={factorOptions}
                onChange={(left) => {
                  const next = [...conditions];
                  next[index] = { ...cond, left };
                  onChange(next);
                }}
              />
              <select
                className={controlClass}
                value={cond.op}
                onChange={(e) => {
                  const op = e.target.value;
                  const nextCond: RuleCondition = { ...cond, op };
                  if (op === "near_pct") {
                    nextCond.pct = Number.isFinite(cond.pct) ? Number(cond.pct) : 3;
                    if (nextCond.right.kind === "const") {
                      nextCond.right = { kind: "factor", factor: "SMA_20" };
                    }
                    if (nextCond.left.kind === "const") {
                      nextCond.left = { kind: "factor", factor: "CLOSE" };
                    }
                  }
                  const next = [...conditions];
                  next[index] = nextCond;
                  onChange(next);
                }}
                aria-label="算子"
              >
                {OPS.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>
              <OperandEditor
                value={cond.right}
                factorOptions={factorOptions}
                forceFactor={cond.op === "near_pct"}
                onChange={(right) => {
                  const next = [...conditions];
                  next[index] = { ...cond, right };
                  onChange(next);
                }}
              />
              {cond.op === "near_pct" ? (
                <label className="flex items-center gap-1 text-xs text-[var(--desk-mist)]">
                  ±
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={`${controlClass} w-20 font-mono`}
                    value={Number.isFinite(cond.pct) ? cond.pct : 3}
                    onChange={(e) => {
                      const next = [...conditions];
                      next[index] = { ...cond, pct: Number(e.target.value) };
                      onChange(next);
                    }}
                    aria-label="贴近百分比"
                  />
                  %
                </label>
              ) : ["gt", "gte", "lt", "lte", "eq"].includes(cond.op) ? (
                <label className="flex items-center gap-1 text-xs text-[var(--desk-mist)]">
                  ×
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={`${controlClass} w-20 font-mono`}
                    value={Number.isFinite(cond.mult) ? cond.mult : 1}
                    onChange={(e) => {
                      const mult = Number(e.target.value);
                      const next = [...conditions];
                      next[index] = {
                        ...cond,
                        mult: Number.isFinite(mult) ? mult : 1,
                      };
                      onChange(next);
                    }}
                    aria-label="右端倍数"
                  />
                </label>
              ) : null}
              <button
                type="button"
                className="text-xs text-[var(--desk-mist)] hover:text-[var(--danger)]"
                onClick={() => onChange(conditions.filter((_, i) => i !== index))}
              >
                删除
              </button>
            </div>
          </li>
        ))}
      </ul>
      <Button
        size="sm"
        variant="secondary"
        className="mt-2"
        onPress={() => onChange([...conditions, emptyCondition()])}
      >
        添加条件
      </Button>
    </>
  );
}

/**
 * 左/右操作数编辑。
 * @param props 当前值与回调
 */
function OperandEditor({
  value,
  factorOptions,
  onChange,
  forceFactor = false,
}: {
  value: Operand;
  factorOptions: FactorOption[];
  onChange: (next: Operand) => void;
  /** near_pct 右侧强制因子 */
  forceFactor?: boolean;
}) {
  const kind = forceFactor ? "factor" : value.kind;
  return (
    <div className="flex min-w-[140px] flex-1 flex-wrap items-center gap-1.5">
      {forceFactor ? null : (
        <select
          className={controlClass}
          value={value.kind}
          onChange={(e) => {
            if (e.target.value === "const") {
              onChange({ kind: "const", const: value.kind === "const" ? value.const : 30 });
            } else {
              onChange({
                kind: "factor",
                factor: value.kind === "factor" ? value.factor : "SMA_5",
              });
            }
          }}
          aria-label="操作数类型"
        >
          <option value="factor">因子</option>
          <option value="const">常数</option>
        </select>
      )}
      {kind === "const" && value.kind === "const" ? (
        <input
          type="number"
          className={`${controlClass} w-24 font-mono`}
          value={value.const}
          onChange={(e) => onChange({ kind: "const", const: Number(e.target.value) })}
        />
      ) : (
        <>
          <FactorOperandCombobox
            value={value.kind === "factor" ? value.factor : "SMA_20"}
            options={factorOptions}
            onChange={(factor) =>
              onChange({
                kind: "factor",
                factor,
                lag: value.kind === "factor" && value.lag ? value.lag : undefined,
              })
            }
          />
          <label className="flex items-center gap-1 text-xs text-[var(--desk-mist)]">
            滞后
            <input
              type="number"
              min={0}
              step={1}
              className={`${controlClass} w-14 font-mono`}
              value={value.kind === "factor" && Number.isFinite(value.lag) ? value.lag : 0}
              onChange={(e) => {
                const lag = Math.max(0, Math.floor(Number(e.target.value) || 0));
                onChange({
                  kind: "factor",
                  factor: value.kind === "factor" ? value.factor : "SMA_20",
                  lag: lag > 0 ? lag : undefined,
                });
              }}
              aria-label="滞后天数"
            />
          </label>
        </>
      )}
    </div>
  );
}

/**
 * 可搜索的因子选择（Combobox）。
 * @param props 当前因子名、选项与回调
 */
function FactorOperandCombobox({
  value,
  options,
  onChange,
}: {
  value: string;
  options: FactorOption[];
  onChange: (factor: string) => void;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);

  const selected = options.find((o) => o.value === value);
  const displayLabel = selected?.label ?? value;
  const filtered = useMemo(
    () => filterFactorOptions(options, open ? query : ""),
    [options, open, query]
  );

  useEffect(() => {
    const onDoc = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    setHighlight(0);
  }, [query, open]);

  /**
   * 确认选中某一因子。
   * @param factor 因子名
   */
  const commit = (factor: string) => {
    onChange(factor);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={wrapRef} className="relative min-w-[120px] flex-1">
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-label="搜索并选择因子"
        className={`${controlClass} w-full font-mono`}
        value={open ? query : displayLabel}
        placeholder="搜索因子"
        autoComplete="off"
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onChange={(e) => {
          setOpen(true);
          setQuery(e.target.value);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setOpen(false);
            setQuery("");
            (e.target as HTMLInputElement).blur();
            return;
          }
          if (!open) {
            if (e.key === "ArrowDown" || e.key === "Enter") {
              e.preventDefault();
              setOpen(true);
              setQuery("");
            }
            return;
          }
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHighlight((h) => Math.min(h + 1, Math.max(filtered.length - 1, 0)));
            return;
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            setHighlight((h) => Math.max(h - 1, 0));
            return;
          }
          if (e.key === "Enter") {
            e.preventDefault();
            const hit = filtered[highlight] ?? filtered[0];
            if (hit) commit(hit.value);
          }
        }}
      />
      {open ? (
        <ul
          className="absolute left-0 top-full z-30 mt-1 max-h-56 w-full min-w-[14rem] overflow-auto rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] shadow-lg"
          role="listbox"
        >
          {value && !options.some((o) => o.value === value) ? (
            <li>
              <button
                type="button"
                className="w-full px-3 py-2 text-left font-mono text-xs text-[var(--desk-mist)] hover:bg-[var(--desk-line)]"
                onMouseDown={(ev) => ev.preventDefault()}
                onClick={() => commit(value)}
              >
                {value}（未在目录）
              </button>
            </li>
          ) : null}
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-sm text-[var(--desk-mist)]">无匹配因子</li>
          ) : (
            filtered.map((opt, index) => (
              <li key={opt.value} role="option" aria-selected={opt.value === value}>
                <button
                  type="button"
                  className={`w-full truncate px-3 py-2 text-left text-sm hover:bg-[var(--desk-line)] ${
                    index === highlight ? "bg-[var(--desk-line)]" : ""
                  } ${opt.value === value ? "text-[var(--desk-accent)]" : "text-[var(--desk-text)]"}`}
                  onMouseDown={(ev) => ev.preventDefault()}
                  onMouseEnter={() => setHighlight(index)}
                  onClick={() => commit(opt.value)}
                >
                  {opt.label}
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
