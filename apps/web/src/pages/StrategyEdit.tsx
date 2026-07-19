import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, formatBeijingTime } from "../api";
import { StrategyCodeEditor } from "./StrategyCodeEditor";
import type { PageLogProps } from "./types";

type StrategySource = "yaml" | "agent" | "python";

type HistoryItem = {
  ts?: string;
  from?: string | null;
  to?: string;
  reason?: string;
};

type StrategyDetail = {
  id: string;
  name: string;
  source: StrategySource | string;
  version: string;
  status: string;
  lifecycle_stage?: string;
  description?: string;
  yaml_body?: string | null;
  lifecycle_history?: HistoryItem[];
};

/** 新建时编辑器占位（不自动塞示例） */
const EMPTY_STUB = `# 在此编写策略正文
# 可点「查看示例」从抽屉采用模板
`;

/**
 * YAML 规则示例：人工写好的可执行规则（保存 → research，可直接回测）。
 */
const EXAMPLE_YAML = `id: breakout_yaml
name: 均线突破-YAML
version: v1.0
symbol: 600519.SH
when:
  sma_fast:
    period: 5
  sma_slow:
    period: 20
then:
  action: signal
params:
  style: trend_follow
  note: 人工维护的声明式规则；保存后可回测 / 纸交易
`;

/**
 * Agent 草稿示例：含假设与风险备注（保存 → draft，需列表「晋级」）。
 */
const EXAMPLE_AGENT = `id: agent_earnings_drift_draft
name: 【待审】财报窗口动量草稿
version: v0.1-draft
symbol: 300750.SZ
# —— 以下为 Agent 生成元数据，晋级前请人工核对 ——
hypothesis: |
  财报披露前后 5 日，短均线相对长均线走强时试多；
  若窗口外波动放大则放弃（草稿，未经验证）。
risk_notes:
  - 未做涨跌停与停牌过滤
  - 样本外夏普未知，禁止直接主力资金
  - 请先回测再晋级孵化
generated_by: desk-agent
confidence: 0.42
when:
  sma_fast:
    period: 3
  sma_slow:
    period: 15
then:
  action: signal
params:
  window: earnings_season
  max_hold_days: 5
  note: Agent 草稿 · 保存后 status=draft，列表页「晋级」后才进生命周期
`;

/** Python 注册策略示例（参考；持久化请改仓库代码后同步） */
const EXAMPLE_PYTHON = `"""双均线示例策略（Python 注册）。"""

from desk_common.contracts import Side, Signal
from desk_strategy import register_strategy


@register_strategy(id="ma_cross", name="双均线-日线(5/20)", version="v1.0")
class MaCross:
    """sma5 上穿 sma20 买、下穿卖。"""

    def on_bar(self, ctx) -> list[Signal]:
        row = ctx["row"] if isinstance(ctx, dict) else ctx.row
        symbol = row.get("symbol", "UNKNOWN")
        fast, slow = row.get("sma_5"), row.get("sma_20")
        prev_fast, prev_slow = row.get("prev_sma_5"), row.get("prev_sma_20")
        if None in (fast, slow, prev_fast, prev_slow):
            return []
        if prev_fast <= prev_slow and fast > slow:
            return [Signal(symbol=symbol, side=Side.BUY, reason="ma_golden_cross")]
        if prev_fast >= prev_slow and fast < slow:
            return [Signal(symbol=symbol, side=Side.SELL, reason="ma_death_cross")]
        return []
`;

const TYPE_OPTIONS: Array<{
  id: StrategySource;
  label: string;
  hint: string;
}> = [
  {
    id: "yaml",
    label: "YAML 规则",
    hint: "声明式规则；保存为 research，阶段重置为孵化。",
  },
  {
    id: "agent",
    label: "Agent 草稿",
    hint: "待审草稿；保存为 draft，阶段重置为孵化，需晋级。",
  },
  {
    id: "python",
    label: "Python 代码",
    hint: "可编辑草稿对照；持久化请改仓库代码后「同步策略」。",
  },
];

const STAGE_LABEL: Record<string, string> = {
  incubating: "孵化",
  paper: "纸交易",
  probation: "试用",
  production: "主力",
  retired: "退役",
};

/**
 * 按类型返回示例正文。
 * @param source 策略来源
 */
function exampleFor(source: StrategySource): string {
  if (source === "agent") return EXAMPLE_AGENT;
  if (source === "python") return EXAMPLE_PYTHON;
  return EXAMPLE_YAML;
}

/**
 * 策略新增 / 编辑：正文自主编辑；示例在抽屉；保存后回到孵化；历史在本页。
 * @param props 页面日志
 */
export default function StrategyEdit({ setLog }: PageLogProps) {
  const navigate = useNavigate();
  const { strategyId } = useParams<{ strategyId: string }>();
  const isNew = !strategyId || strategyId === "new";

  const [source, setSource] = useState<StrategySource>("yaml");
  const [body, setBody] = useState(EMPTY_STUB);
  const [meta, setMeta] = useState<StrategyDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const [exampleOpen, setExampleOpen] = useState(false);

  const typeMeta = useMemo(
    () => TYPE_OPTIONS.find((t) => t.id === source) || TYPE_OPTIONS[0],
    [source]
  );

  const editorLanguage = source === "python" ? "python" : "yaml";

  const history = useMemo(() => {
    const list = meta?.lifecycle_history || [];
    return [...list].reverse();
  }, [meta]);

  /**
   * 编辑模式：拉取元数据 + 源码填入编辑框。
   */
  useEffect(() => {
    if (isNew) {
      setSource("yaml");
      setBody(EMPTY_STUB);
      setMeta(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const [row, srcPayload] = await Promise.all([
          api<StrategyDetail>(`/api/strategies/${encodeURIComponent(strategyId!)}`),
          api<{ language: string; text: string; source: string }>(
            `/api/strategies/${encodeURIComponent(strategyId!)}/source`
          ),
        ]);
        if (cancelled) return;
        const src = (row.source || srcPayload.source || "yaml") as StrategySource;
        const text = srcPayload.text || row.yaml_body || EMPTY_STUB;
        setMeta(row);
        setSource(src === "agent" || src === "python" ? src : "yaml");
        setBody(text);
        setLog(`已加载策略 ${row.id} 源码`);
      } catch (error) {
        if (!cancelled) {
          setLog(String(error));
          navigate("/strategies");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isNew, strategyId, navigate, setLog]);

  useEffect(() => {
    if (!exampleOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExampleOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [exampleOpen]);

  /**
   * 切换类型：不覆盖正文，仅改保存方式。
   */
  const onSelectType = (next: StrategySource) => {
    if (!isNew && source !== next) {
      setLog("编辑模式不可更改策略来源类型");
      return;
    }
    setSource(next);
  };

  /**
   * 采用抽屉中的示例到编辑器。
   */
  const adoptExample = () => {
    setBody(exampleFor(source));
    setExampleOpen(false);
    setLog(`已采用「${typeMeta.label}」示例`);
  };

  /**
   * 保存后刷新元数据与编辑器正文。
   */
  const reloadAfterSave = async (id: string) => {
    const [row, srcPayload] = await Promise.all([
      api<StrategyDetail>(`/api/strategies/${encodeURIComponent(id)}`),
      api<{ text: string }>(`/api/strategies/${encodeURIComponent(id)}/source`).catch(() => ({
        text: body,
      })),
    ]);
    setMeta(row);
    setBody(srcPayload.text || body);
    return row;
  };

  /**
   * 保存：YAML/Agent 写入正文；Python 从仓库同步注册表。
   */
  const save = async () => {
    if (source === "python") {
      setBusy(true);
      try {
        const r = await api<{ synced: number }>("/api/strategies/sync-python", {
          method: "POST",
        });
        setLog(`已保存：同步 Python 策略 ${r.synced} 个（请先在仓库改代码再保存）`);
        if (!isNew && strategyId) await reloadAfterSave(strategyId);
      } catch (error) {
        setLog(String(error));
      } finally {
        setBusy(false);
      }
      return;
    }
    const text = body.trim();
    if (!text || text.startsWith("# 在此编写")) {
      setLog("请先编写策略正文，或从示例抽屉采用模板");
      return;
    }
    setBusy(true);
    try {
      if (source === "agent") {
        const saved = await api<StrategyDetail>("/api/strategies/draft", {
          method: "POST",
          body: JSON.stringify({ payload: { yaml_body: body } }),
        });
        await reloadAfterSave(saved.id);
        setLog(`已保存草稿 ${saved.id}，阶段已重置为孵化`);
        if (isNew) navigate(`/strategies/${encodeURIComponent(saved.id)}/edit`);
      } else {
        const saved = await api<StrategyDetail>("/api/strategies/from-yaml", {
          method: "POST",
          body: JSON.stringify({ yaml_body: body }),
        });
        await reloadAfterSave(saved.id);
        setLog(`已保存 ${saved.id}，阶段已重置为孵化`);
        if (isNew) navigate(`/strategies/${encodeURIComponent(saved.id)}/edit`);
      }
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="p-8 text-sm text-[var(--desk-mist)]">加载策略…</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-wrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">
              {isNew ? "新增策略" : "编辑策略"}
            </CardTitle>
            {!isNew && meta ? (
              <>
                <Chip size="sm" variant="soft" className="font-mono">
                  {meta.id}
                </Chip>
                <Chip size="sm" variant="soft">
                  {STAGE_LABEL[meta.lifecycle_stage || ""] || meta.lifecycle_stage || "—"}
                </Chip>
                <Chip size="sm" variant="soft">
                  {meta.status}
                </Chip>
              </>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button size="sm" variant="secondary" onPress={() => navigate("/strategies")}>
              返回列表
            </Button>
            <Button size="sm" variant="secondary" onPress={() => setExampleOpen(true)}>
              查看示例
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void save()}>
              {busy
                ? "保存中…"
                : source === "agent"
                  ? "保存草稿"
                  : "保存策略"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <div>
            <div className="mb-2 text-xs text-[var(--desk-mist)]">策略类型</div>
            <div role="tablist" aria-label="策略类型" className="flex flex-wrap gap-2">
              {TYPE_OPTIONS.map((opt) => {
                const active = source === opt.id;
                const locked = !isNew && source !== opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    disabled={locked}
                    onClick={() => onSelectType(opt.id)}
                    className={[
                      "rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                      active
                        ? "border-[var(--desk-accent)] bg-[var(--desk-ink)] text-[var(--desk-text)]"
                        : "border-[var(--desk-line)] text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
                      locked ? "cursor-not-allowed opacity-40" : "",
                    ].join(" ")}
                  >
                    <div className="font-medium">{opt.label}</div>
                    <div className="mt-0.5 max-w-[14rem] text-xs opacity-80">{opt.hint}</div>
                  </button>
                );
              })}
            </div>
          </div>

          <p className="text-xs text-[var(--desk-mist)]">
            {typeMeta.hint} 示例请点「查看示例」。YAML/Agent 保存编辑框正文；Python
            需先改仓库代码再点「保存策略」同步。保存后生命周期回到孵化。
          </p>

          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-[var(--desk-text)]">策略正文</div>
            <Chip size="sm" variant="soft">
              {editorLanguage === "python" ? "Python" : "YAML"}
            </Chip>
          </div>
          <StrategyCodeEditor
            value={body}
            language={editorLanguage}
            height="420px"
            onChange={setBody}
          />
        </CardContent>
      </Card>

      {!isNew ? (
        <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
          <CardHeader className="flex w-full flex-row items-center justify-between gap-3 p-5 pb-3">
            <CardTitle className="text-base text-[var(--desk-text)]">阶段迁移历史</CardTitle>
            <Chip size="sm" variant="soft">
              {history.length} 条
            </Chip>
          </CardHeader>
          <CardContent className="p-5 pt-2">
            {!history.length ? (
              <p className="text-sm text-[var(--desk-mist)]">暂无记录</p>
            ) : (
              <ul className="space-y-2 text-sm text-[var(--desk-mist)]">
                {history.map((h, i) => (
                  <li
                    key={`${h.ts}-${i}`}
                    className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2"
                  >
                    <div className="font-mono text-xs">{formatBeijingTime(h.ts)}</div>
                    <div className="mt-1 text-[var(--desk-text)]">
                      {STAGE_LABEL[h.from || ""] || h.from || "—"} →{" "}
                      {STAGE_LABEL[h.to || ""] || h.to || "—"}
                    </div>
                    <div className="mt-0.5 text-xs">{h.reason || ""}</div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}

      {exampleOpen ? (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            className="absolute inset-0 cursor-default bg-black/50"
            aria-label="关闭示例抽屉"
            onClick={() => setExampleOpen(false)}
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label={`${typeMeta.label}示例`}
            className="relative z-10 ml-auto flex h-full w-full max-w-xl flex-col border-l border-[var(--desk-line)] bg-[var(--desk-panel)] shadow-2xl"
          >
            <div className="flex items-center justify-between gap-3 border-b border-[var(--desk-line)] px-5 py-4">
              <div>
                <div className="text-base font-medium text-[var(--desk-text)]">
                  {typeMeta.label} · 示例
                </div>
                <p className="mt-0.5 text-xs text-[var(--desk-mist)]">
                  预览模板，点「采用示例」写入左侧编辑区（可再改）
                </p>
              </div>
              <Button size="sm" variant="ghost" onPress={() => setExampleOpen(false)}>
                关闭
              </Button>
            </div>
            <pre className="flex-1 overflow-auto whitespace-pre-wrap break-words bg-[var(--desk-ink)] p-5 font-mono text-xs leading-6 text-[var(--desk-text)]">
              {exampleFor(source)}
            </pre>
            <div className="flex justify-end gap-2 border-t border-[var(--desk-line)] px-5 py-4">
              <Button size="sm" variant="secondary" onPress={() => setExampleOpen(false)}>
                取消
              </Button>
              <Button size="sm" variant="primary" onPress={adoptExample}>
                采用示例
              </Button>
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
