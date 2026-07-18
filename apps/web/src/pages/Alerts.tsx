import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

type AlertItem = {
  id: number;
  category: string;
  title: string;
  body: string;
  status: string;
  created_at: string;
};

type CategoryFilter = "all" | string;

/**
 * 告警中心：结构化告警流、状态摘要与演示发送。
 * @param props 页面日志写入方法
 */
export default function Alerts({ setLog }: PageLogProps) {
  const [rows, setRows] = useState<AlertItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [statusFilter, setStatusFilter] = useState<CategoryFilter>("all");
  const [title, setTitle] = useState("演示告警");
  const [body, setBody] = useState("来自告警中心的手动推送");

  /**
   * 拉取最近告警。
   */
  const load = async () => {
    setBusy(true);
    try {
      const data = await api<AlertItem[]>("/api/alerts");
      setRows(data);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const categories = useMemo(() => {
    const set = new Set(rows.map((row) => row.category || "other"));
    return ["all", ...Array.from(set).sort()];
  }, [rows]);

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      if (category !== "all" && (row.category || "other") !== category) return false;
      if (statusFilter !== "all" && normalizeStatus(row.status) !== statusFilter) {
        return false;
      }
      return true;
    });
  }, [rows, category, statusFilter]);

  const stats = useMemo(() => {
    const total = rows.length;
    let sent = 0;
    let failed = 0;
    let logged = 0;
    let other = 0;
    for (const row of rows) {
      const key = normalizeStatus(row.status);
      if (key === "sent") sent += 1;
      else if (key === "failed") failed += 1;
      else if (key === "logged_only" || key === "deduped" || key === "skipped") logged += 1;
      else other += 1;
    }
    return { total, sent, failed, logged, other };
  }, [rows]);

  /**
   * 发送告警（演示 / 自定义文案）。
   */
  const send = async () => {
    const trimmedTitle = title.trim() || "演示告警";
    const trimmedBody = body.trim() || "来自前端";
    setBusy(true);
    try {
      const result = await api<{ status?: string; id?: number }>("/api/alerts/send", {
        method: "POST",
        body: JSON.stringify({
          title: trimmedTitle,
          body: trimmedBody,
          category: "manual",
          dedupe_key: `ui-${Date.now()}`,
        }),
      });
      setLog(`告警已处理：${result.status ?? "ok"}${result.id != null ? ` #${result.id}` : ""}`);
      await load();
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">告警中心</CardTitle>
            <Chip size="sm" variant="soft" color="accent">
              {stats.total} 条
            </Chip>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              刷新
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void send()}>
              {busy ? "发送中…" : "发送告警"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="全部" value={String(stats.total)} />
            <Stat label="已发送" value={String(stats.sent)} tone="success" />
            <Stat label="失败" value={String(stats.failed)} tone="danger" />
            <Stat label="仅记录/跳过" value={String(stats.logged + stats.other)} tone="mist" />
          </div>

          <div className="grid gap-3 md:grid-cols-[1fr_1.2fr]">
            <label className="block space-y-1.5">
              <span className="text-xs text-[var(--desk-mist)]">标题</span>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className={inputClass}
                placeholder="告警标题"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs text-[var(--desk-mist)]">正文</span>
              <input
                value={body}
                onChange={(event) => setBody(event.target.value)}
                className={inputClass}
                placeholder="告警正文"
              />
            </label>
          </div>
          <p className="text-xs text-[var(--desk-mist)]">
            未配置飞书 Webhook 时会以 <code>logged_only</code> 落库；同去重键 5 分钟内不重复发送。
          </p>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-col items-stretch gap-3 p-5 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base text-[var(--desk-text)]">告警流</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <FilterGroup
              label="分类"
              value={category}
              options={categories.map((item) => ({
                value: item,
                label: item === "all" ? "全部" : item,
              }))}
              onChange={setCategory}
            />
            <FilterGroup
              label="状态"
              value={statusFilter}
              options={[
                { value: "all", label: "全部" },
                { value: "sent", label: "已发送" },
                { value: "failed", label: "失败" },
                { value: "logged_only", label: "仅记录" },
                { value: "deduped", label: "去重" },
                { value: "skipped", label: "跳过" },
              ]}
              onChange={setStatusFilter}
            />
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {!filtered.length ? (
            <div className="rounded-lg border border-dashed border-[var(--desk-line)] bg-[var(--desk-ink)] px-4 py-10 text-center">
              <p className="text-sm text-[var(--desk-text)]">暂无匹配告警</p>
              <p className="mt-1 text-xs text-[var(--desk-mist)]">
                可调整筛选，或点击「发送告警」写入一条演示记录。
              </p>
            </div>
          ) : (
            <ul className="space-y-0 divide-y divide-[var(--desk-line)]">
              {filtered.map((row, index) => (
                <li
                  key={row.id}
                  className="group grid gap-3 py-4 first:pt-1 last:pb-1 md:grid-cols-[7rem_1fr_auto] md:items-start"
                  style={{
                    animation: "desk-alert-in 280ms ease both",
                    animationDelay: `${Math.min(index, 8) * 30}ms`,
                  }}
                >
                  <div className="space-y-1">
                    <div className="font-mono text-xs text-[var(--desk-mist)]">
                      {formatClock(row.created_at)}
                    </div>
                    <div className="text-[11px] text-[var(--desk-mist)]/80">
                      {formatRelative(row.created_at)}
                    </div>
                  </div>
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-[var(--desk-text)]">
                        {row.title || "（无标题）"}
                      </span>
                      <Chip size="sm" variant="soft">
                        {row.category || "other"}
                      </Chip>
                      <StatusChip status={row.status} />
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--desk-mist)]">
                      {row.body || "—"}
                    </p>
                  </div>
                  <div className="font-mono text-xs text-[var(--desk-mist)] md:pt-0.5">
                    #{row.id}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <style>{`
        @keyframes desk-alert-in {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          li[style] { animation: none !important; }
        }
      `}</style>
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 摘要指标块。
 */
function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "danger" | "mist";
}) {
  const color =
    tone === "success"
      ? "text-[var(--success)]"
      : tone === "danger"
        ? "text-[var(--danger)]"
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

/**
 * 筛选按钮组。
 */
function FilterGroup({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
      <span className="mr-1 text-xs text-[var(--desk-mist)]">{label}</span>
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={[
              "rounded-md px-2.5 py-1 text-xs transition-colors",
              active
                ? "bg-[var(--desk-accent)] text-[var(--desk-panel)]"
                : "bg-[var(--desk-ink)] text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
            ].join(" ")}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * 告警投递状态徽标。
 */
function StatusChip({ status }: { status: string }) {
  const key = normalizeStatus(status);
  const color =
    key === "sent"
      ? "success"
      : key === "failed"
        ? "danger"
        : key === "deduped"
          ? "warning"
          : "accent";
  const label =
    key === "sent"
      ? "已发送"
      : key === "failed"
        ? "失败"
        : key === "logged_only"
          ? "仅记录"
          : key === "deduped"
            ? "去重"
            : key === "skipped"
              ? "跳过"
              : status;
  return (
    <Chip size="sm" variant="soft" color={color as "success" | "danger" | "warning" | "accent"}>
      {label}
    </Chip>
  );
}

/**
 * 归一化状态前缀（failed:xxx → failed）。
 */
function normalizeStatus(status: string): string {
  if (!status) return "other";
  if (status.startsWith("failed")) return "failed";
  return status;
}

/**
 * 格式化时分秒（本地）。
 */
function formatClock(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  return `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}

/**
 * 相对时间文案。
 */
function formatRelative(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const delta = Date.now() - date.getTime();
  const sec = Math.floor(delta / 1000);
  if (sec < 60) return "刚刚";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour} 小时前`;
  const day = Math.floor(hour / 24);
  if (day < 7) return `${day} 天前`;
  return "";
}
