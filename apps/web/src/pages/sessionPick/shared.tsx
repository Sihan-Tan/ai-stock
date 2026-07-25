import { Button, Chip } from "@heroui/react";
import type { ComponentProps, ReactNode } from "react";

export type SessionKind = "morning" | "closing";

const SESSION_META: Record<
  SessionKind,
  { label: string; window: string; tip: string; accentClass: string }
> = {
  morning: {
    label: "早盘选股",
    window: "开盘前 · 竞价",
    tip: "基于在市标的竞价快照选拔强势板块 / 个股，一键写入自选。",
    accentClass: "border-l-[var(--desk-signal)]",
  },
  closing: {
    label: "尾盘选股",
    window: "约 14:40",
    tip: "按标记策略扫买点，筛次日预埋候选，一键写入自选。",
    accentClass: "border-l-[var(--desk-accent)]",
  },
};

type SessionHeroProps = {
  kind: SessionKind;
  asof?: string;
  busy?: boolean;
  metrics?: Array<{ label: string; value: string | number }>;
  actions: ReactNode;
};

/**
 * 早盘 / 尾盘共用页头：场次标签、日期、指标与操作区。
 * @param props 场次与操作
 */
export function SessionHero({ kind, asof, busy, metrics, actions }: SessionHeroProps) {
  const meta = SESSION_META[kind];
  return (
    <section
      className={`overflow-hidden rounded-xl border border-[var(--desk-line)] bg-[var(--desk-panel)] border-l-4 ${meta.accentClass}`}
    >
      <div className="flex flex-col gap-4 p-5 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--desk-text)]">
              {meta.label}
            </h1>
            <Chip size="sm" variant="soft">
              {meta.window}
            </Chip>
            {asof && (
              <Chip size="sm" variant="soft">
                {asof}
              </Chip>
            )}
            {busy && (
              <span className="text-xs text-[var(--desk-mist)]" aria-live="polite">
                运行中…
              </span>
            )}
          </div>
          <p className="max-w-xl text-sm leading-relaxed text-[var(--desk-mist)]">{meta.tip}</p>
          {metrics && metrics.length > 0 && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 pt-1">
              {metrics.map((m) => (
                <div key={m.label} className="flex items-baseline gap-1.5">
                  <span className="font-mono text-lg tabular-nums text-[var(--desk-text)]">
                    {m.value}
                  </span>
                  <span className="text-xs text-[var(--desk-mist)]">{m.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 md:justify-end">{actions}</div>
      </div>
    </section>
  );
}

type SessionPanelProps = {
  title: string;
  hint?: string;
  action?: ReactNode;
  children: ReactNode;
};

/**
 * 选股页内容面板。
 * @param props 标题、提示与内容
 */
export function SessionPanel({ title, hint, action, children }: SessionPanelProps) {
  return (
    <section className="rounded-xl border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--desk-line)] px-5 py-4">
        <div>
          <h2 className="text-sm font-medium text-[var(--desk-text)]">{title}</h2>
          {hint && <p className="mt-1 text-xs leading-relaxed text-[var(--desk-mist)]">{hint}</p>}
        </div>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

type SessionBriefProps = {
  title: string;
  content?: string;
  emptyHint?: string;
};

/**
 * 选股摘要文案块。
 * @param props 标题与正文
 */
export function SessionBrief({ title, content, emptyHint = "暂无内容，先运行选拔。" }: SessionBriefProps) {
  return (
    <div className="rounded-lg bg-[var(--desk-ink)] px-4 py-3">
      <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--desk-mist)]">
        {title}
      </div>
      <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-[var(--desk-text)]/90">
        {content || emptyHint}
      </pre>
    </div>
  );
}

type SessionTableProps = {
  children: ReactNode;
};

/**
 * 选股结果表外层。
 * @param props 表格内容
 */
export function SessionTable({ children }: SessionTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--desk-line)]">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

/**
 * 表头单元格样式。
 */
export const thClass =
  "bg-[var(--desk-ink)] px-3 py-2.5 text-xs font-medium text-[var(--desk-mist)]";

/**
 * 表体单元格样式。
 */
export const tdClass = "px-3 py-3 align-middle";

/**
 * 可点击行样式。
 */
export const trClickClass =
  "cursor-pointer border-t border-[var(--desk-line)] transition-colors hover:bg-[var(--desk-ink)]/80";

type EmptyRowProps = {
  colSpan: number;
  message: string;
};

/**
 * 空表提示行。
 * @param props 列数与文案
 */
export function EmptyRow({ colSpan, message }: EmptyRowProps) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-10 text-center text-sm text-[var(--desk-mist)]">
        {message}
      </td>
    </tr>
  );
}

type EmptyPickNoticeProps = {
  /** 主标题 */
  title: string;
  /** 说明与下一步建议 */
  tip: string;
};

/**
 * 未选出符合条件股票时的醒目提示。
 * @param props 标题与说明
 */
export function EmptyPickNotice({ title, tip }: EmptyPickNoticeProps) {
  return (
    <div
      role="status"
      className="rounded-xl border border-[var(--desk-warn-border)] bg-[var(--desk-warn-bg)] px-4 py-3"
    >
      <div className="text-sm font-medium text-[var(--desk-warn-fg)]">{title}</div>
      <p className="mt-1 text-xs leading-relaxed text-[var(--desk-warn-fg)]/85">{tip}</p>
    </div>
  );
}

type StrategyChipProps = {
  id: string;
  name: string;
  selected: boolean;
  tagged?: boolean;
  onToggle: (id: string, selected: boolean) => void;
};

/**
 * 尾盘策略可选芯片。
 * @param props 策略与选中态
 */
export function StrategyChip({ id, name, selected, tagged, onToggle }: StrategyChipProps) {
  return (
    <button
      type="button"
      onClick={() => onToggle(id, !selected)}
      className={[
        "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
        selected
          ? "border-[var(--desk-accent)] bg-[var(--desk-ink)] text-[var(--desk-text)]"
          : "border-[var(--desk-line)] bg-transparent text-[var(--desk-mist)] hover:border-[var(--desk-mist)] hover:text-[var(--desk-text)]",
      ].join(" ")}
      aria-pressed={selected}
    >
      <span
        className={[
          "inline-block size-2 shrink-0 rounded-full",
          selected ? "bg-[var(--desk-accent)]" : "bg-[var(--desk-line)]",
        ].join(" ")}
        aria-hidden
      />
      <span className="min-w-0">
        <span className="block truncate font-medium">{name || id}</span>
        <span className="block truncate font-mono text-[11px] opacity-70">{id}</span>
      </span>
      {tagged && (
        <Chip size="sm" variant="soft">
          尾盘
        </Chip>
      )}
    </button>
  );
}

/**
 * 次要操作按钮快捷包装。
 */
export function SecondaryAction({
  children,
  ...rest
}: ComponentProps<typeof Button>) {
  return (
    <Button size="sm" variant="secondary" {...rest}>
      {children}
    </Button>
  );
}

/**
 * 主操作按钮快捷包装。
 */
export function PrimaryAction({
  children,
  ...rest
}: ComponentProps<typeof Button>) {
  return (
    <Button size="sm" variant="primary" {...rest}>
      {children}
    </Button>
  );
}

/**
 * 竞价/涨跌幅（小数 → 百分数）。
 * @param value 小数涨幅
 */
export function formatPct(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

/**
 * 得分展示。
 * @param value 分数
 */
export function formatScore(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

/**
 * 金额缩写。
 * @param value 金额
 */
export function formatCompact(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`;
  if (Math.abs(value) >= 10_000) return `${(value / 10_000).toFixed(2)}万`;
  return value.toFixed(0);
}
