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
];

const controlClass =
  "rounded-md border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 py-1.5 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 默认空条件。
 */
function emptyCondition(): RuleCondition {
  return {
    op: "gt",
    left: { kind: "factor", factor: "SMA_5" },
    right: { kind: "factor", factor: "SMA_20" },
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
    }
  };

  dumpSide("buy", doc.buy);
  dumpSide("sell", doc.sell);
  return `${lines.join("\n")}\n`;
}

/**
 * 从 YAML 文本尽力解析规则文档（仅支持本构建器产出格式）。
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
    const side = section === "buy" ? { ...base.buy, conditions: [] as RuleCondition[] } : { ...base.sell, conditions: [] as RuleCondition[] };
    const blockRe = new RegExp(`(?:^|\\n)${section}:\\n([\\s\\S]*?)(?=\\n(?:buy|sell):|\\s*$)`);
    const block = text.match(blockRe)?.[1] ?? "";
    const combineM = block.match(/combine:\s*(all|any)/);
    if (combineM) side.combine = combineM[1] as "all" | "any";
    const condBlocks = block.split(/\n\s*-\s+op:\s*/).slice(1);
    for (const raw of condBlocks) {
      const opM = raw.match(/^([a-z_]+)/);
      const leftFactor = raw.match(/left:\s*\n\s+factor:\s*(.+)/);
      const leftConst = raw.match(/left:\s*\n\s+const:\s*([-\d.]+)/);
      const rightFactor = raw.match(/right:\s*\n\s+factor:\s*(.+)/);
      const rightConst = raw.match(/right:\s*\n\s+const:\s*([-\d.]+)/);
      const op = opM?.[1] || "gt";
      const left: Operand = leftConst
        ? { kind: "const", const: Number(leftConst[1]) }
        : { kind: "factor", factor: unquote(leftFactor?.[1] || "SMA_5") };
      const right: Operand = rightConst
        ? { kind: "const", const: Number(rightConst[1]) }
        : { kind: "factor", factor: unquote(rightFactor?.[1] || "SMA_20") };
      side.conditions.push({ op, left, right });
    }
    return side;
  };

  base.buy = parseSide("buy");
  base.sell = parseSide("sell");
  return base;
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
 * 规则构建器因子下拉文案：因子名（说明）。
 * @param name 因子名
 * @param label 说明（API label）
 */
export function formatFactorOptionLabel(name: string, label: string): string {
  const tip = (label || "").trim();
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
          label: formatFactorOptionLabel(f.name, f.label),
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
                  const conditions = [...side.conditions];
                  conditions[index] = { ...cond, op: e.target.value };
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
                onChange={(right) => {
                  const conditions = [...side.conditions];
                  conditions[index] = { ...cond, right };
                  onChange({ ...side, conditions });
                }}
              />
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
}: {
  value: Operand;
  factorOptions: Array<{ value: string; label: string }>;
  onChange: (next: Operand) => void;
}) {
  return (
    <div className="flex min-w-[140px] flex-1 flex-wrap items-center gap-1.5">
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
      {value.kind === "const" ? (
        <input
          type="number"
          className={`${controlClass} w-24 font-mono`}
          value={value.const}
          onChange={(e) => onChange({ kind: "const", const: Number(e.target.value) })}
        />
      ) : (
        <select
          className={`${controlClass} min-w-[120px] flex-1`}
          value={value.factor}
          onChange={(e) => onChange({ kind: "factor", factor: e.target.value })}
        >
          {!factorOptions.some((o) => o.value === value.factor) ? (
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
