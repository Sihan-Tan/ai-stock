import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { FactorMeta } from "../factors/types";
import type { PageLogProps } from "./types";

type Operand =
  | { kind: "factor"; factor: string }
  | { kind: "const"; const: number };

type RuleCondition = {
  op: string;
  left: Operand;
  right: Operand;
  /** near_pct 专用：±百分比，默认 3 */
  pct?: number;
};

type RuleSide = {
  combine: "all" | "any";
  conditions: RuleCondition[];
};

type RuleDoc = {
  id: string;
  name: string;
  version: string;
  kind: "factor_rules";
  buy: RuleSide;
  sell: RuleSide;
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
 * 默认规则文档。
 */
function defaultDoc(): RuleDoc {
  return {
    id: "rule_new",
    name: "新规则策略",
    version: "v1.0",
    kind: "factor_rules",
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
  return `${indent}factor: ${JSON.stringify(op.factor || "SMA_5")}`;
}

/**
 * 将规则文档序列化为 YAML（手写，避免依赖 js-yaml）。
 * @param doc 规则文档
 */
export function dumpFactorRulesYaml(doc: RuleDoc): string {
  const lines: string[] = [
    `id: ${JSON.stringify(doc.id.trim() || "rule_new")}`,
    `name: ${JSON.stringify(doc.name.trim() || "规则策略")}`,
    `version: ${JSON.stringify(doc.version.trim() || "v1.0")}`,
    `kind: factor_rules`,
  ];

  /**
   * @param key buy|sell
   * @param side 条件组
   */
  const dumpSide = (key: "buy" | "sell", side: RuleSide) => {
    lines.push(`${key}:`);
    lines.push(`  combine: ${side.combine === "any" ? "any" : "all"}`);
    lines.push(`  conditions:`);
    if (side.conditions.length === 0) {
      lines.push(`    []`);
      return;
    }
    for (const cond of side.conditions) {
      lines.push(`    - op: ${cond.op}`);
      lines.push(`      left:`);
      lines.push(dumpOperand(cond.left, "        "));
      lines.push(`      right:`);
      lines.push(dumpOperand(cond.right, "        "));
      if (cond.op === "near_pct") {
        const pct = Number.isFinite(cond.pct) ? Number(cond.pct) : 3;
        lines.push(`      pct: ${pct}`);
      }
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

  /**
   * @param section buy|sell
   */
  const parseSide = (section: "buy" | "sell"): RuleSide => {
    const side =
      section === "buy"
        ? { ...base.buy, conditions: [] as RuleCondition[] }
        : { ...base.sell, conditions: [] as RuleCondition[] };
    const blockRe = new RegExp(`(?:^|\\n)${section}:\\n([\\s\\S]*?)(?=\\n(?:buy|sell|id|name|version|kind|params):|\\s*$)`);
    const block = text.match(blockRe)?.[1] ?? "";
    const combineM = block.match(/combine:\s*(all|any)/);
    if (combineM) side.combine = combineM[1] as "all" | "any";
    if (/conditions:\s*\[\s*\]/.test(block)) {
      return side;
    }
    // 兼容「- op:」与 PyYAML 键序「- left:」等：按列表项切分
    const condBlocks = block.split(/\n\s*-\s+/).slice(1);
    for (const raw of condBlocks) {
      const opM = raw.match(/(?:^|\n)\s*op:\s*([a-z_]+)/) || raw.match(/^op:\s*([a-z_]+)/m);
      const left = parseOperand(raw, "left") ?? { kind: "factor" as const, factor: "SMA_5" };
      const right = parseOperand(raw, "right") ?? { kind: "factor" as const, factor: "SMA_20" };
      const op = opM?.[1] || "gt";
      const pctM = raw.match(/(?:^|\n)\s*pct:\s*([-\d.]+)/);
      const cond: RuleCondition = { op, left, right };
      if (op === "near_pct") {
        cond.pct = pctM ? Number(pctM[1]) : 3;
      }
      side.conditions.push(cond);
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
    new RegExp(`${side}:\\s*\\{\\s*factor:\\s*([^,}]+)\\s*\\}`)
  );
  if (flowFactor) {
    return { kind: "factor", factor: unquote(flowFactor[1]) };
  }
  const flowConst = raw.match(
    new RegExp(`${side}:\\s*\\{\\s*const:\\s*([-\\d.]+)\\s*\\}`)
  );
  if (flowConst) {
    return { kind: "const", const: Number(flowConst[1]) };
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
 * 规则构建器因子下拉文案：因子名（中文说明）。
 * @param name 因子名
 * @param label 短标签
 * @param description 中文说明（优先）
 */
export function formatFactorOptionLabel(
  name: string,
  label: string,
  description?: string
): string {
  const tip = (description || label || "").trim();
  if (!tip || tip === name) return name;
  return `${name}（${tip}）`;
}

/**
 * 策略规则构建器：因子比较 / 交叉 → factor_rules YAML。
 * @param props 页面日志
 */
export default function StrategyRuleBuilder({ setLog }: PageLogProps) {
  const navigate = useNavigate();
  const { strategyId } = useParams();
  const isNew = !strategyId;
  const [doc, setDoc] = useState<RuleDoc>(() => defaultDoc());
  const [factors, setFactors] = useState<FactorMeta[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!isNew);

  const factorOptions = useMemo(
    () =>
      factors
        .filter((f) => f.enabled)
        .map((f) => ({
          value: f.name,
          label: formatFactorOptionLabel(f.name, f.label, f.description),
        })),
    [factors]
  );

  useEffect(() => {
    void api<{ factors: FactorMeta[] }>("/api/factors")
      .then((res) => setFactors(res.factors ?? []))
      .catch((error) => setLog(String(error)));
  }, [setLog]);

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
      setLog("买卖条件不能都为空");
      return;
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
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void save()}>
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
          <p className="text-xs text-[var(--desk-mist)]">
            买/卖各一组条件；同 bar 同时满足时卖优先。保存后可在回测页选用。
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
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
  factorOptions: Array<{ value: string; label: string }>;
  onChange: (next: RuleSide) => void;
}) {
  return (
    <section className="space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)]/30 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-[var(--desk-text)]">{title}</h3>
        <select
          className={controlClass}
          value={side.combine}
          onChange={(e) =>
            onChange({ ...side, combine: e.target.value === "any" ? "any" : "all" })
          }
          aria-label={`${title}组合方式`}
        >
          <option value="all">全部满足 (AND)</option>
          <option value="any">任一满足 (OR)</option>
        </select>
      </div>
      <ul className="space-y-2">
        {side.conditions.map((cond, index) => (
          <li
            key={index}
            className="space-y-2 rounded-md border border-[var(--desk-line)] bg-[var(--desk-panel)]/40 p-2.5"
          >
            <div className="flex flex-wrap items-center gap-2">
              <OperandEditor
                value={cond.left}
                factorOptions={factorOptions}
                onChange={(left) => {
                  const conditions = [...side.conditions];
                  conditions[index] = { ...cond, left };
                  onChange({ ...side, conditions });
                }}
              />
              <select
                className={controlClass}
                value={cond.op}
                onChange={(e) => {
                  const op = e.target.value;
                  const conditions = [...side.conditions];
                  const next: RuleCondition = { ...cond, op };
                  if (op === "near_pct") {
                    next.pct = Number.isFinite(cond.pct) ? Number(cond.pct) : 3;
                    if (next.right.kind === "const") {
                      next.right = { kind: "factor", factor: "SMA_20" };
                    }
                    if (next.left.kind === "const") {
                      next.left = { kind: "factor", factor: "CLOSE" };
                    }
                  }
                  conditions[index] = next;
                  onChange({ ...side, conditions });
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
                  const conditions = [...side.conditions];
                  conditions[index] = { ...cond, right };
                  onChange({ ...side, conditions });
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
                      const conditions = [...side.conditions];
                      conditions[index] = { ...cond, pct: Number(e.target.value) };
                      onChange({ ...side, conditions });
                    }}
                    aria-label="贴近百分比"
                  />
                  %
                </label>
              ) : null}
              <button
                type="button"
                className="text-xs text-[var(--desk-mist)] hover:text-[var(--danger)]"
                onClick={() => {
                  const conditions = side.conditions.filter((_, i) => i !== index);
                  onChange({ ...side, conditions });
                }}
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
        onPress={() => onChange({ ...side, conditions: [...side.conditions, emptyCondition()] })}
      >
        添加条件
      </Button>
    </section>
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
  factorOptions: Array<{ value: string; label: string }>;
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
        <select
          className={`${controlClass} min-w-[120px] flex-1`}
          value={value.kind === "factor" ? value.factor : "SMA_20"}
          onChange={(e) => onChange({ kind: "factor", factor: e.target.value })}
        >
          {value.kind === "factor" && !factorOptions.some((o) => o.value === value.factor) ? (
            <option value={value.factor}>{value.factor}</option>
          ) : null}
          {factorOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
