import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { PageLogProps } from "./types";

type Strategy = {
  id: string;
  version: string;
  name: string;
  source: string;
  status: string;
  yaml_body?: string | null;
};

const DEFAULT_YAML = `id: my_breakout
name: 均线突破-自定义
version: v0.1
symbol: 600519.SH
when:
  sma_fast:
    period: 5
  sma_slow:
    period: 20
then:
  action: signal
params:
  note: 从策略页保存的 YAML
`;

/**
 * 策略管理：清单、YAML 编辑、草稿晋级、软/硬删除。
 * @param props 页面日志写入方法
 */
export default function Strategies({ setLog }: PageLogProps) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<Strategy[]>([]);
  const [busy, setBusy] = useState(false);
  const [yamlBody, setYamlBody] = useState(DEFAULT_YAML);
  const [asDraft, setAsDraft] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  /**
   * 拉取策略列表。
   */
  const load = () => {
    const qs = showArchived ? "?include_archived=true" : "";
    return api<Strategy[]>(`/api/strategies${qs}`)
      .then(setRows)
      .catch((error) => setLog(String(error)));
  };

  /**
   * 同步 Python 策略并加载仓库内 YAML 示例。
   */
  const syncJobs = async () => {
    setBusy(true);
    try {
      await api("/api/strategies/sync-python", { method: "POST" });
      await api("/api/strategies/load-yaml-file", { method: "POST" }).catch(() => null);
      await load();
      setLog("已同步策略列表");
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 保存 YAML 策略。
   */
  const saveYaml = async () => {
    setBusy(true);
    try {
      if (asDraft) {
        await api("/api/strategies/draft", {
          method: "POST",
          body: JSON.stringify({ payload: { yaml_body: yamlBody } }),
        });
        setLog("已保存为 Agent 草稿（draft）");
      } else {
        await api("/api/strategies/from-yaml", {
          method: "POST",
          body: JSON.stringify({ yaml_body: yamlBody }),
        });
        setLog("YAML 策略已保存");
      }
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 草稿晋级为 research。
   * @param strategyId 策略 ID
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
   * @param row 策略行
   */
  const remove = async (row: Strategy) => {
    const hard = row.status === "archived";
    const ok = window.confirm(
      hard
        ? `确定彻底删除「${row.id}」？此操作不可恢复。`
        : `确定软删除「${row.id}」？可在勾选「显示已软删除」后再次删除以彻底移除。`
    );
    if (!ok) return;
    setBusy(true);
    try {
      const result = await api<{ action: string; strategy_id: string }>(
        `/api/strategies/${encodeURIComponent(row.id)}`,
        { method: "DELETE" }
      );
      setLog(
        result.action === "hard"
          ? `已彻底删除：${result.strategy_id}`
          : `已软删除：${result.strategy_id}`
      );
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 将行内 YAML 载入编辑器。
   * @param row 策略行
   */
  const loadIntoEditor = (row: Strategy) => {
    if (row.yaml_body) {
      setYamlBody(row.yaml_body);
      setLog(`已载入 ${row.id} 的 YAML`);
    } else {
      setLog(`${row.id} 无 YAML 正文（Python 策略请直接去回测）`);
    }
  };

  useEffect(() => {
    void load();
  }, [showArchived]);

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">策略清单</CardTitle>
            <Chip variant="soft" color="accent">
              {rows.length} 个
            </Chip>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-3">
            <label className="flex items-center gap-2 text-sm text-[var(--desk-mist)]">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
              />
              显示已软删除
            </label>
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              刷新
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void syncJobs()}>
              同步策略
            </Button>
            <Button size="sm" variant="secondary" onPress={() => navigate("/backtest")}>
              去回测
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
                <tr>
                  <th className="px-3 py-2 font-medium">ID</th>
                  <th className="px-3 py-2 font-medium">名称</th>
                  <th className="px-3 py-2 font-medium">来源</th>
                  <th className="px-3 py-2 font-medium">版本</th>
                  <th className="px-3 py-2 font-medium">状态</th>
                  <th className="px-3 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={`${row.id}-${row.version}`}
                    className={[
                      "border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]",
                      row.status === "archived" ? "opacity-60" : "",
                    ].join(" ")}
                  >
                    <td className="px-3 py-3 font-mono">{row.id}</td>
                    <td className="px-3 py-3">{row.name}</td>
                    <td className="px-3 py-3">{row.source}</td>
                    <td className="px-3 py-3 font-mono">{row.version}</td>
                    <td className="px-3 py-3">
                      <StatusChip status={row.status} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
                        {row.yaml_body ? (
                          <Button size="sm" variant="ghost" onPress={() => loadIntoEditor(row)}>
                            编辑 YAML
                          </Button>
                        ) : null}
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
                        {row.status !== "archived" ? (
                          <Button
                            size="sm"
                            variant="primary"
                            onPress={() =>
                              navigate(`/backtest?strategy_id=${encodeURIComponent(row.id)}`)
                            }
                          >
                            回测
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant={row.status === "archived" ? "danger" : "ghost"}
                          isDisabled={busy}
                          onPress={() => void remove(row)}
                        >
                          {row.status === "archived" ? "彻底删除" : "删除"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                      暂无策略。点击「同步策略」加载 Python / YAML 示例。
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
          <CardTitle className="text-base text-[var(--desk-text)]">YAML 策略编辑</CardTitle>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-[var(--desk-mist)]">
              <input
                type="checkbox"
                checked={asDraft}
                onChange={(event) => setAsDraft(event.target.checked)}
              />
              保存为草稿
            </label>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void saveYaml()}>
              保存 YAML
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <textarea
            value={yamlBody}
            onChange={(event) => setYamlBody(event.target.value)}
            spellCheck={false}
            className="min-h-[280px] w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4 font-mono text-xs leading-6 text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]"
          />
          <p className="mt-2 text-xs text-[var(--desk-mist)]">
            保存走 <code>POST /api/strategies/from-yaml</code>；勾选草稿则走{" "}
            <code>/draft</code>（需晋级后才适合模拟/实盘）。删除：首次软删，勾选「显示已软删除」后可彻底删除。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * 策略状态徽标。
 * @param props.status 状态值
 */
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
