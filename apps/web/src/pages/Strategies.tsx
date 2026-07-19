import { Button, Card, CardContent, CardHeader, CardTitle, Chip, Dropdown } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { PageLogProps } from "./types";

type StrategyKpi = {
  rolling_30d_sharpe?: number;
  rolling_30d_return?: number;
  rolling_30d_maxdd?: number;
  days_since_promotion?: number;
  consecutive_low_sharpe_days?: number;
  total_trades?: number;
  win_rate?: number;
  walk_forward_is_oos_ratio?: number;
};

type Strategy = {
  id: string;
  version: string;
  name: string;
  source: string;
  status: string;
  lifecycle_stage?: string;
  description?: string;
  capital_pct?: number;
  capital_allocated?: number;
  kpi?: StrategyKpi;
  lifecycle_history?: Array<{ ts?: string; from?: string | null; to?: string; reason?: string }>;
  yaml_body?: string | null;
};

type LifecycleSummary = {
  total_capital: number;
  allocated_pct: number;
  idle_pct: number;
  stage_labels: Record<string, string>;
  by_stage: Record<string, Strategy[]>;
};

const STAGE_OPTIONS = [
  { value: "incubating", label: "孵化" },
  { value: "paper", label: "纸交易" },
  { value: "probation", label: "试用" },
  { value: "production", label: "主力" },
  { value: "retired", label: "退役" },
] as const;

/**
 * 策略管理：列表、生命周期阶段 / KPI 评估；新增与编辑见独立页。
 * @param props 页面日志写入方法
 */
export default function Strategies({ setLog }: PageLogProps) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<Strategy[]>([]);
  const [summary, setSummary] = useState<LifecycleSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [abA, setAbA] = useState("");
  const [abB, setAbB] = useState("");

  /**
   * 拉取策略列表与生命周期汇总。
   */
  const load = async () => {
    const qs = showArchived ? "?include_archived=true" : "";
    try {
      const [list, life] = await Promise.all([
        api<Strategy[]>(`/api/strategies${qs}`),
        api<LifecycleSummary>("/api/strategies/lifecycle/summary"),
      ]);
      setRows(list);
      setSummary(life);
      if (!abA && list[0]) setAbA(list[0].id);
      if (!abB && list[1]) setAbB(list[1].id);
    } catch (error) {
      setLog(String(error));
    }
  };

  /**
   * 同步 Python 策略并加载仓库内 YAML 示例。
   */
  const syncJobs = async () => {
    setBusy(true);
    try {
      await api("/api/strategies/sync-python", { method: "POST" });
      await api("/api/strategies/load-yaml-file", { method: "POST" }).catch(() => null);
      const restored = await api<{ restored: number }>("/api/strategies/lifecycle/restore", {
        method: "POST",
      }).catch(() => ({ restored: 0 }));
      await load();
      setLog(
        restored.restored
          ? `已同步策略列表，并恢复 ${restored.restored} 个隐藏策略`
          : "已同步策略列表",
      );
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 仅恢复被误隐藏的策略。
   */
  const restoreHidden = async () => {
    setBusy(true);
    try {
      const result = await api<{ restored: number }>("/api/strategies/lifecycle/restore", {
        method: "POST",
      });
      setLog(`已恢复 ${result.restored} 个策略到列表`);
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 按 KPI 自动评估并迁移生命周期阶段。
   */
  const evaluate = async () => {
    setBusy(true);
    try {
      const result = await api<{
        migrations: Array<{ strategy_id: string; from: string; to: string; reason: string }>;
        summary: LifecycleSummary;
      }>("/api/strategies/lifecycle/evaluate", { method: "POST" });
      setSummary(result.summary);
      const n = result.migrations?.length ?? 0;
      setLog(
        n
          ? `评估完成：${n} 个阶段迁移\n${result.migrations
              .map((m) => `${m.strategy_id}: ${m.from} → ${m.to}（${m.reason}）`)
              .join("\n")}`
          : "评估完成：本轮无阶段变更",
      );
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 对策略跑 Walk-Forward 并写入 KPI。
   * @param strategyId 策略 ID
   */
  const runWalkForward = async (strategyId: string) => {
    setBusy(true);
    try {
      const result = await api<{
        status: string;
        message?: string;
        walk_forward_is_oos_ratio?: number;
        is_sharpe?: number | null;
        oos_sharpe?: number | null;
        symbol?: string;
      }>(`/api/strategies/${encodeURIComponent(strategyId)}/lifecycle/walk-forward`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (result.status === "ok") {
        setLog(
          `WF ${strategyId}@${result.symbol || "—"}: IS/OOS=${(result.walk_forward_is_oos_ratio ?? 0).toFixed(2)}` +
            ` (IS Sharpe ${result.is_sharpe ?? "—"} / OOS ${result.oos_sharpe ?? "—"})`
        );
      } else {
        setLog(`WF 失败: ${result.message || result.status}`);
      }
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 手动调整阶段。
   */
  const changeStage = async (strategyId: string, stage: string) => {
    setBusy(true);
    try {
      await api(`/api/strategies/${encodeURIComponent(strategyId)}/lifecycle/stage`, {
        method: "POST",
        body: JSON.stringify({ stage, reason: "策略管理页手动调整" }),
      });
      setLog(`${strategyId} 阶段 → ${stageLabel(stage, summary)}`);
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * A/B 评估。
   */
  const runAb = async () => {
    if (!abA || !abB || abA === abB) {
      setLog("请选择两个不同的策略做 A/B 评估");
      return;
    }
    setBusy(true);
    try {
      const result = await api<{ verdict: string; msg?: string; winner?: string }>(
        "/api/strategies/lifecycle/ab-test",
        {
          method: "POST",
          body: JSON.stringify({ strategy_a: abA, strategy_b: abB, days_so_far: 30 }),
        },
      );
      setLog(result.msg || `A/B 结果：${result.verdict}${result.winner ? `，胜者 ${result.winner}` : ""}`);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 草稿晋级为 research / 孵化。
   */
  const promote = async (strategyId: string) => {
    setBusy(true);
    try {
      await api(`/api/strategies/${encodeURIComponent(strategyId)}/promote`, {
        method: "POST",
      });
      setLog(`已晋级：${strategyId}`);
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 删除策略：首次软删，已软删则硬删。
   */
  const remove = async (row: Strategy) => {
    const hard = row.status === "archived" || row.lifecycle_stage === "retired";
    const ok = window.confirm(
      hard
        ? `确定彻底删除「${row.id}」？此操作不可恢复。`
        : `确定软删除「${row.id}」并退役？可在勾选「显示已软删除」后再次删除以彻底移除。`,
    );
    if (!ok) return;
    setBusy(true);
    try {
      const result = await api<{ action: string; strategy_id: string }>(
        `/api/strategies/${encodeURIComponent(row.id)}`,
        { method: "DELETE" },
      );
      setLog(
        result.action === "hard"
          ? `已彻底删除：${result.strategy_id}`
          : `已软删除并退役：${result.strategy_id}`,
      );
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
  }, [showArchived]);

  const filteredRows = useMemo(() => {
    if (stageFilter === "all") return rows;
    return rows.filter((row) => (row.lifecycle_stage || "incubating") === stageFilter);
  }, [rows, stageFilter]);

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of rows) {
      const key = row.lifecycle_stage || "incubating";
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [rows]);

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">策略生命周期</CardTitle>
            <Chip variant="soft" color="accent">
              {rows.length} 个
            </Chip>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              刷新
            </Button>
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void syncJobs()}>
              同步策略
            </Button>
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void restoreHidden()}>
              恢复隐藏
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void evaluate()}>
              {busy ? "评估中…" : "评估并迁移"}
            </Button>
            <Button size="sm" variant="primary" onPress={() => navigate("/strategies/new")}>
              新增策略
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-2">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="总资金基准"
              value={fmtMoney(summary?.total_capital ?? 1_000_000)}
            />
            <Stat
              label="已分配"
              value={`${((summary?.allocated_pct ?? 0) * 100).toFixed(1)}%`}
              tone="accent"
            />
            <Stat
              label="闲置"
              value={`${((summary?.idle_pct ?? 1) * 100).toFixed(1)}%`}
              tone="mist"
            />
            <Stat label="主力策略" value={String(stageCounts.production || 0)} tone="success" />
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-[var(--desk-mist)]">
            {STAGE_OPTIONS.map((opt) => (
              <span key={opt.value}>
                {opt.label} {stageCounts[opt.value] || 0}
              </span>
            ))}
          </div>
          <p className="text-xs text-[var(--desk-mist)]">
            生命周期：孵化 → 纸交易 → 试用 → 主力 → 退役。评估按 KPI（回测 Sharpe / 收益 / 回撤 /
            IS·OOS 等）自动晋级或退役，并建议资金占比。
          </p>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-col items-stretch gap-3 p-5 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">策略列表</CardTitle>
            <Chip size="sm" variant="soft">
              {filteredRows.length} 条
            </Chip>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-sm text-[var(--desk-mist)]">
              阶段
              <select
                value={stageFilter}
                onChange={(e) => setStageFilter(e.target.value)}
                className={selectClass}
              >
                <option value="all">全部</option>
                {STAGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--desk-mist)]">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
              />
              显示已软删除
            </label>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-3 py-2 font-medium">策略</th>
                  <th className="px-3 py-2 font-medium">阶段</th>
                  <th className="px-3 py-2 font-medium">资金</th>
                  <th className="px-3 py-2 font-medium">评估 KPI</th>
                  <th className="px-3 py-2 font-medium">状态</th>
                  <th className="px-3 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const kpi = row.kpi || {};
                  return (
                    <tr
                      key={`${row.id}-${row.version}`}
                      className={[
                        "border-b border-[var(--desk-line)] hover:bg-[var(--desk-ink)]",
                        row.status === "archived" || row.lifecycle_stage === "retired"
                          ? "opacity-60"
                          : "",
                      ].join(" ")}
                    >
                      <td className="px-3 py-3">
                        <div className="font-mono text-xs text-[var(--desk-mist)]">{row.id}</div>
                        <div className="text-[var(--desk-text)]">{row.name}</div>
                        <div className="mt-0.5 text-[11px] text-[var(--desk-mist)]">
                          {row.source} · {row.version}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <select
                          className={`${selectClass} block`}
                          value={row.lifecycle_stage || "incubating"}
                          disabled={busy}
                          onChange={(e) => void changeStage(row.id, e.target.value)}
                          aria-label={`${row.id} 阶段`}
                        >
                          {STAGE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-3 font-mono text-xs text-[var(--desk-mist)]">
                        <div>{((row.capital_pct ?? 0) * 100).toFixed(1)}%</div>
                        <div>{fmtMoney(row.capital_allocated ?? 0)}</div>
                      </td>
                      <td className="px-3 py-3 text-xs text-[var(--desk-mist)]">
                        <div>Sharpe {(kpi.rolling_30d_sharpe ?? 0).toFixed(2)}</div>
                        <div>收益 {fmtPct(kpi.rolling_30d_return ?? 0)}</div>
                        <div>回撤 {fmtPct(kpi.rolling_30d_maxdd ?? 0)}</div>
                        <div>
                          WF {(kpi.walk_forward_is_oos_ratio ?? 0).toFixed(2)}
                          <span className="text-[10px]"> (点 WF 重算)</span>
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <StatusChip status={row.status} />
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {row.status === "draft" ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              isDisabled={busy}
                              onPress={() => void promote(row.id)}
                            >
                              晋级
                            </Button>
                          ) : null}
                          <Button
                            size="sm"
                            variant="ghost"
                            isDisabled={busy}
                            onPress={() => void runWalkForward(row.id)}
                          >
                            WF
                          </Button>
                          <Dropdown>
                            <Dropdown.Trigger
                              className="inline-flex h-8 items-center rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 text-xs text-[var(--desk-text)] hover:border-[var(--desk-mist)]"
                              aria-label={`${row.id} 更多操作`}
                            >
                              操作 ▾
                            </Dropdown.Trigger>
                            <Dropdown.Popover placement="bottom end" className="min-w-[8rem]">
                              <Dropdown.Menu
                                aria-label={`${row.id} 操作菜单`}
                                onAction={(key) => {
                                  if (key === "edit") {
                                    navigate(`/strategies/${encodeURIComponent(row.id)}/edit`);
                                  } else if (key === "delete") {
                                    void remove(row);
                                  }
                                }}
                              >
                                <Dropdown.Item id="edit" textValue="编辑">
                                  编辑
                                </Dropdown.Item>
                                <Dropdown.Item
                                  id="delete"
                                  textValue="删除"
                                  className="text-[var(--danger,#ef4444)]"
                                >
                                  {row.status === "archived" ||
                                  row.lifecycle_stage === "retired"
                                    ? "彻底删除"
                                    : "删除"}
                                </Dropdown.Item>
                              </Dropdown.Menu>
                            </Dropdown.Popover>
                          </Dropdown>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!filteredRows.length && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                      暂无策略。可「同步策略」或「新增策略」。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">A/B 评估</CardTitle>
          <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void runAb()}>
            比较 Sharpe
          </Button>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3 p-5 pt-2">
          <label className="space-y-1 text-xs text-[var(--desk-mist)]">
            策略 A
            <select value={abA} onChange={(e) => setAbA(e.target.value)} className={`${selectClass} block min-w-[12rem]`}>
              {rows.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs text-[var(--desk-mist)]">
            策略 B
            <select value={abB} onChange={(e) => setAbB(e.target.value)} className={`${selectClass} block min-w-[12rem]`}>
              {rows.map((r) => (
                <option key={`b-${r.id}`} value={r.id}>
                  {r.id}
                </option>
              ))}
            </select>
          </label>
          <p className="w-full text-xs text-[var(--desk-mist)]">
            比较双方 30 日 Sharpe；差距 &lt; 0.2 视为不显著。需先有 KPI（回测或评估填充）。
          </p>
        </CardContent>
      </Card>

    </div>
  );
}

const selectClass =
  "rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2 py-1 text-xs text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)] disabled:opacity-60";

/**
 * 阶段中文名。
 */
function stageLabel(stage: string, summary: LifecycleSummary | null): string {
  return summary?.stage_labels?.[stage] || STAGE_OPTIONS.find((o) => o.value === stage)?.label || stage;
}

function fmtMoney(n: number): string {
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(2)}%`;
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "accent" | "mist";
}) {
  const color =
    tone === "success"
      ? "text-[var(--success)]"
      : tone === "accent"
        ? "text-[var(--desk-accent)]"
        : tone === "mist"
          ? "text-[var(--desk-mist)]"
          : "text-[var(--desk-text)]";
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-4 py-3">
      <div className="text-xs text-[var(--desk-mist)]">{label}</div>
      <div className={`mt-1 font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  const color =
    status === "live"
      ? "danger"
      : status === "paper" || status === "archived"
        ? "warning"
        : status === "draft"
          ? "accent"
          : "success";
  return (
    <Chip size="sm" variant="soft" color={color as "danger" | "warning" | "accent" | "success"}>
      {status}
    </Chip>
  );
}
