import { Button, Chip } from "@heroui/react";
import { useEffect, useMemo, useState, type ComponentProps, type ReactNode } from "react";

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

type SessionRunStatus = "idle" | "running" | "done";

type SessionHeroProps = {
  kind: SessionKind;
  asof?: string;
  /** 是否正在跑选拔 / 精选 */
  busy?: boolean;
  /** 是否已有本场次结果（用于「完成 / 未开始」） */
  hasRun?: boolean;
  metrics?: Array<{ label: string; value: string | number }>;
  actions: ReactNode;
};

/**
 * 页头运行状态：未开始 / 运行中 / 完成。
 * @param busy 进行中
 * @param hasRun 已有结果
 */
function resolveSessionRunStatus(busy?: boolean, hasRun?: boolean): SessionRunStatus {
  if (busy) return "running";
  if (hasRun) return "done";
  return "idle";
}

const RUN_STATUS_CHIP: Record<
  SessionRunStatus,
  { label: string; color?: "warning" | "success" | "accent" }
> = {
  idle: { label: "未开始" },
  running: { label: "运行中", color: "warning" },
  done: { label: "完成", color: "success" },
};

/**
 * 早盘 / 尾盘共用页头：场次标签、日期、运行状态与操作区。
 * @param props 场次与操作
 */
export function SessionHero({ kind, asof, busy, hasRun, metrics, actions }: SessionHeroProps) {
  const meta = SESSION_META[kind];
  const runStatus = resolveSessionRunStatus(busy, hasRun);
  const statusChip = RUN_STATUS_CHIP[runStatus];
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
            <Chip
              size="sm"
              variant="soft"
              color={statusChip.color}
              aria-live="polite"
            >
              {statusChip.label}
            </Chip>
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

/** 初选个股表默认每页条数 */
export const SESSION_STOCK_PAGE_SIZE = 10;

type SessionPagerProps = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
};

/**
 * 表格底部分页：上一页 / 下一页。
 * @param props 页码与总数
 */
export function SessionPager({ page, pageSize, total, onPageChange }: SessionPagerProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize) || 1);
  const safePage = Math.min(Math.max(1, page), pageCount);
  if (total <= pageSize) return null;
  const from = (safePage - 1) * pageSize + 1;
  const to = Math.min(total, safePage * pageSize);
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--desk-mist)]">
      <span>
        第 {from}–{to} 条，共 {total} 条
      </span>
      <div className="flex items-center gap-2">
        <SecondaryAction
          isDisabled={safePage <= 1}
          onPress={() => onPageChange(safePage - 1)}
        >
          上一页
        </SecondaryAction>
        <span className="font-mono text-[var(--desk-text)]">
          {safePage}/{pageCount}
        </span>
        <SecondaryAction
          isDisabled={safePage >= pageCount}
          onPress={() => onPageChange(safePage + 1)}
        >
          下一页
        </SecondaryAction>
      </div>
    </div>
  );
}

/**
 * 列表分页切片；items 变化时自动回到第 1 页。
 * @param items 全量数据
 * @param pageSize 每页条数
 */
export function usePagedItems<T>(items: T[], pageSize: number = SESSION_STOCK_PAGE_SIZE) {
  const [page, setPage] = useState(1);
  const signature = `${items.length}:${pageSize}`;
  useEffect(() => {
    setPage(1);
  }, [signature]);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize) || 1);
  const safePage = Math.min(Math.max(1, page), pageCount);
  const slice = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, pageSize, safePage]);
  return { page: safePage, setPage, pageSize, total: items.length, slice };
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

/** 投研精选单条结果 */
export type ResearchPickRow = {
  symbol?: string;
  name?: string;
  score?: number;
  confidence?: number;
  rationale?: string;
  rank?: number;
  buy_low?: number;
  buy_high?: number;
  target_low?: number;
  target_high?: number;
  stop_loss?: number;
};

type ResearchPicksPanelProps = {
  picks: ResearchPickRow[];
  busy?: boolean;
  /** 面板右上角自定义操作；未传且提供 onRun 时渲染默认「投研精选」按钮 */
  action?: ReactNode;
  onRun?: () => void;
  emptyHint?: string;
  /** 点击行打开详情时的代码 */
  onRowClick?: (symbol: string) => void;
};

/**
 * 投研精选结果表（早盘 / 尾盘共用）。
 * @param props picks / busy / onRun / action / emptyHint / onRowClick
 */
export function ResearchPicksPanel({
  picks,
  busy,
  action,
  onRun,
  emptyHint = "暂无投研精选。先完成选拔后再点「投研精选」。",
  onRowClick,
}: ResearchPicksPanelProps) {
  const headerAction =
    action ??
    (onRun ? (
      <SecondaryAction isDisabled={busy} onPress={() => void onRun()}>
        投研精选
      </SecondaryAction>
    ) : undefined);

  return (
    <SessionPanel
      title="投研精选"
      hint="基于原筛选候选，经 LLM 打分；每只须含买入区间、目标价区间与止损价。"
      action={headerAction}
    >
      <SessionTable>
        <thead>
          <tr>
            <th className={thClass}>#</th>
            <th className={thClass}>代码</th>
            <th className={thClass}>名称</th>
            <th className={thClass}>score</th>
            <th className={thClass}>confidence</th>
            <th className={thClass}>买入区间</th>
            <th className={thClass}>目标价</th>
            <th className={thClass}>止损</th>
            <th className={thClass}>理由</th>
          </tr>
        </thead>
        <tbody>
          {picks.map((pick, index) => {
            const symbol = pick.symbol || "";
            const clickable = Boolean(onRowClick && symbol);
            return (
              <tr
                key={`${symbol}-${pick.rank ?? index}`}
                className={clickable ? trClickClass : "border-t border-[var(--desk-line)]"}
                onClick={() => clickable && onRowClick?.(symbol)}
              >
                <td className={`${tdClass} font-mono text-[var(--desk-mist)]`}>
                  {pick.rank ?? index + 1}
                </td>
                <td className={`${tdClass} font-mono text-[var(--desk-text)]`}>
                  {symbol || "—"}
                </td>
                <td className={tdClass}>{pick.name || "—"}</td>
                <td className={`${tdClass} font-mono`}>{formatScore(pick.score)}</td>
                <td className={`${tdClass} font-mono`}>{formatScore(pick.confidence)}</td>
                <td className={`${tdClass} font-mono`}>
                  {formatPriceRange(pick.buy_low, pick.buy_high)}
                </td>
                <td className={`${tdClass} font-mono`}>
                  {formatPriceRange(pick.target_low, pick.target_high)}
                </td>
                <td className={`${tdClass} font-mono`}>{formatPrice(pick.stop_loss)}</td>
                <td className={`${tdClass} max-w-md text-[var(--desk-mist)]`}>
                  {pick.rationale || "—"}
                </td>
              </tr>
            );
          })}
          {!picks.length && <EmptyRow colSpan={9} message={emptyHint} />}
        </tbody>
      </SessionTable>
    </SessionPanel>
  );
}

/**
 * 单价展示。
 * @param value 价格（元）
 */
export function formatPrice(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

/**
 * 价格区间展示。
 * @param low 下限
 * @param high 上限
 */
export function formatPriceRange(low?: number, high?: number): string {
  if (low == null || high == null || Number.isNaN(low) || Number.isNaN(high)) return "—";
  return `${low.toFixed(2)}–${high.toFixed(2)}`;
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
