import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

type CalendarEventItem = {
  id: number;
  event_date: string;
  event_time?: string;
  category: string;
  importance: number;
  title: string;
  summary?: string;
  symbol?: string;
  name?: string;
  region?: string;
  source?: string;
};

type SuspensionRow = {
  symbol: string;
  name?: string | null;
  event_type: string;
  effective_date: string;
  reason?: string | null;
  scope?: string | null;
};

type CategoryFilter = "all" | "news" | "macro" | "earnings" | "lockup" | "ipo" | "catalyst";

const CATEGORY_LABEL: Record<string, string> = {
  news: "新闻",
  macro: "宏观",
  earnings: "财报",
  lockup: "解禁",
  ipo: "IPO",
  catalyst: "催化",
};

/**
 * 交易日历：当日重大新闻 + 停牌提醒 + 按月加载的财经日历/催化剂。
 * @param props 页面日志写入方法
 */
export default function Calendar({ setLog }: PageLogProps) {
  const today = useMemo(() => new Date(), []);
  const todayKey = useMemo(() => formatDateKey(today), [today]);
  const monthOptions = useMemo(() => buildMonthOptions(today, 3), [today]);
  const [selectedMonth, setSelectedMonth] = useState(monthOptions[0]?.key ?? "");
  const [todayEvents, setTodayEvents] = useState<CalendarEventItem[]>([]);
  const [horizonEvents, setHorizonEvents] = useState<CalendarEventItem[]>([]);
  const [horizonMeta, setHorizonMeta] = useState<{ start: string; end: string } | null>(null);
  const [suspensions, setSuspensions] = useState<SuspensionRow[]>([]);
  const [nextTradeDay, setNextTradeDay] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [horizonBusy, setHorizonBusy] = useState(false);
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [query, setQuery] = useState("");

  /**
   * 按月份拉取财经日历与催化剂。
   */
  const loadHorizon = async (monthKey: string) => {
    if (!monthKey) return;
    setHorizonBusy(true);
    try {
      const range = monthRange(monthKey, today);
      const horizonBody = await api<{ start: string; end: string; items: CalendarEventItem[] }>(
        `/api/calendar/events?start=${range.start}&end=${range.end}&months=3`,
      );
      setHorizonEvents(horizonBody.items ?? []);
      setHorizonMeta({ start: horizonBody.start, end: horizonBody.end });
    } catch (error) {
      setLog(String(error));
    } finally {
      setHorizonBusy(false);
    }
  };

  /**
   * 拉取今日重大、停牌与当前所选月份事件。
   */
  const load = async (monthKey = selectedMonth) => {
    setBusy(true);
    try {
      const [todayBody, suspended, next] = await Promise.all([
        api<{ asof: string; items: CalendarEventItem[] }>("/api/calendar/events/today"),
        api<SuspensionRow[]>("/api/calendar/suspensions"),
        api<{ next_trade_day: string }>("/api/calendar/next-trade-day").catch(() => null),
      ]);
      setTodayEvents(todayBody.items ?? []);
      setSuspensions(suspended);
      setNextTradeDay(next?.next_trade_day ?? null);
      await loadHorizon(monthKey);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 强制同步财经事件源。
   */
  const syncEvents = async () => {
    setBusy(true);
    try {
      const result = await api<{ synced: number; source: string }>("/api/calendar/events/sync?months=3", {
        method: "POST",
      });
      setLog(`财经事件已同步：${result.synced} 条（来源 ${result.source}）`);
      await load(selectedMonth);
    } catch (error) {
      setLog(String(error));
      setBusy(false);
    }
  };

  /**
   * 切换月份后按需加载。
   */
  const onMonthChange = (monthKey: string) => {
    setSelectedMonth(monthKey);
    setQuery("");
    void loadHorizon(monthKey);
  };

  useEffect(() => {
    void load(monthOptions[0]?.key ?? "");
    // 仅首屏加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredHorizon = useMemo(() => {
    const q = query.trim().toLowerCase();
    return horizonEvents.filter((item) => {
      if (category !== "all" && item.category !== category) return false;
      if (!q) return true;
      const hay = `${item.title} ${item.summary ?? ""} ${item.symbol ?? ""} ${item.name ?? ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [horizonEvents, category, query]);

  const selectedMonthLabel =
    monthOptions.find((item) => item.key === selectedMonth)?.label ?? selectedMonth;

  const stats = useMemo(() => {
    const macro = horizonEvents.filter((e) => e.category === "macro").length;
    const catalyst = horizonEvents.filter((e) =>
      ["catalyst", "earnings", "lockup", "ipo"].includes(e.category),
    ).length;
    return {
      todayMajor: todayEvents.length,
      horizon: horizonEvents.length,
      macro,
      catalyst,
    };
  }, [todayEvents, horizonEvents]);

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">交易日历</CardTitle>
            <Chip size="sm" variant="soft" color="accent">
              今日重大 · 未来 3 个月
            </Chip>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              {busy ? "加载中…" : "刷新"}
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy} onPress={() => void syncEvents()}>
              同步事件
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-2">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="今日重大" value={String(stats.todayMajor)} tone="accent" />
            <Stat label="当月事件" value={String(stats.horizon)} />
            <Stat label="宏观财经" value={String(stats.macro)} tone="success" />
            <Stat label="催化/财报/解禁" value={String(stats.catalyst)} />
          </div>
          <p className="text-xs text-[var(--desk-mist)]">
            展示当日重大新闻；财经日历与催化剂按月份下拉加载（未来 3 个月内可选）。
            {horizonMeta ? ` 当前窗口 ${horizonMeta.start} → ${horizonMeta.end}。` : ""}
            {nextTradeDay ? ` 下一交易日 ${nextTradeDay}。` : ""}
            外部源不可用时自动使用演示数据。
          </p>
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">停牌提醒</CardTitle>
            <Chip size="sm" variant="soft">
              {suspensions.length} 条
            </Chip>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {!suspensions.length ? (
            <Empty title="暂无停牌记录" hint="可在行情同步任务中补充停牌数据源。" />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-[var(--desk-line)]">
              <table className="w-full min-w-[560px] border-collapse text-left text-sm">
                <thead className="bg-[var(--desk-ink)] text-xs text-[var(--desk-mist)]">
                  <tr>
                    <th className="px-3 py-2.5 font-medium">生效日</th>
                    <th className="px-3 py-2.5 font-medium">标的</th>
                    <th className="px-3 py-2.5 font-medium">类型</th>
                    <th className="px-3 py-2.5 font-medium">原因</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--desk-line)]">
                  {suspensions.map((row, index) => (
                    <tr key={`${row.symbol}-${row.effective_date}-${index}`}>
                      <td className="px-3 py-2.5 font-mono text-xs text-[var(--desk-mist)]">
                        {row.effective_date}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="font-mono text-xs text-[var(--desk-mist)]">{row.symbol}</div>
                        <div>{row.name || "—"}</div>
                      </td>
                      <td className="px-3 py-2.5 text-[var(--desk-mist)]">{row.event_type}</td>
                      <td className="px-3 py-2.5 text-[var(--desk-mist)]">{row.reason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">今日重大新闻 / 事件</CardTitle>
            <Chip size="sm" variant="soft">
              {todayKey}
            </Chip>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {!todayEvents.length ? (
            <Empty
              title="今日暂无重大事件"
              hint="点击「同步事件」拉取财经源，或确认演示种子已写入。"
            />
          ) : (
            <ul className="space-y-0 divide-y divide-[var(--desk-line)]">
              {todayEvents.map((item, index) => (
                <li
                  key={item.id}
                  className="grid gap-2 py-4 first:pt-1 last:pb-1 md:grid-cols-[5.5rem_1fr_auto] md:items-start"
                  style={{
                    animation: "desk-cal-in 260ms ease both",
                    animationDelay: `${Math.min(index, 8) * 28}ms`,
                  }}
                >
                  <div className="space-y-1">
                    <div className="font-mono text-xs text-[var(--desk-mist)]">
                      {item.event_time || "全天"}
                    </div>
                    <ImportanceDots value={item.importance} />
                  </div>
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-[var(--desk-text)]">{item.title}</span>
                      <CategoryChip category={item.category} />
                      {item.region ? (
                        <Chip size="sm" variant="soft">
                          {item.region}
                        </Chip>
                      ) : null}
                    </div>
                    <p className="text-sm leading-relaxed text-[var(--desk-mist)]">
                      {item.summary || "—"}
                    </p>
                  </div>
                  <div className="font-mono text-[11px] text-[var(--desk-mist)]/80">{item.source}</div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-col items-stretch gap-3 p-5 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">财经日历与催化剂</CardTitle>
            <Chip size="sm" variant="soft">
              {selectedMonthLabel}
            </Chip>
            <Chip size="sm" variant="soft">
              {horizonBusy ? "加载中…" : `${filteredHorizon.length} 条`}
            </Chip>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5">
              <span className="text-xs text-[var(--desk-mist)]">月份</span>
              <select
                value={selectedMonth}
                onChange={(event) => onMonthChange(event.target.value)}
                disabled={busy || horizonBusy}
                className={selectClass}
                aria-label="选择财经日历月份"
              >
                {monthOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <FilterGroup
              label="类型"
              value={category}
              options={[
                { value: "all", label: "全部" },
                { value: "macro", label: "宏观" },
                { value: "news", label: "新闻" },
                { value: "earnings", label: "财报" },
                { value: "lockup", label: "解禁" },
                { value: "ipo", label: "IPO" },
                { value: "catalyst", label: "催化" },
              ]}
              onChange={(value) => setCategory(value as CategoryFilter)}
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className={inputClass}
              placeholder="搜索标题 / 标的 / 摘要"
              aria-label="搜索财经事件"
            />
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          {horizonBusy ? (
            <Empty title="正在加载该月事件…" hint="切换月份将按需请求对应区间数据。" />
          ) : !filteredHorizon.length ? (
            <Empty title="该月暂无事件" hint="可切换月份或类型筛选，或点击「同步事件」。" />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-[var(--desk-line)]">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead className="bg-[var(--desk-ink)] text-xs text-[var(--desk-mist)]">
                  <tr>
                    <th className="px-3 py-2.5 font-medium">日期</th>
                    <th className="px-3 py-2.5 font-medium">类型</th>
                    <th className="px-3 py-2.5 font-medium">事件</th>
                    <th className="px-3 py-2.5 font-medium">标的</th>
                    <th className="px-3 py-2.5 font-medium">重要</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--desk-line)]">
                  {filteredHorizon.map((item, index) => (
                    <tr
                      key={item.id}
                      className="bg-[var(--desk-panel)] transition-colors hover:bg-[var(--desk-ink)]"
                      style={{
                        animation: "desk-cal-in 240ms ease both",
                        animationDelay: `${Math.min(index, 12) * 18}ms`,
                      }}
                    >
                      <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs text-[var(--desk-mist)]">
                        <div>{item.event_date.slice(5)}</div>
                        <div className="text-[10px] opacity-80">{item.event_time || "—"}</div>
                      </td>
                      <td className="px-3 py-2.5">
                        <CategoryChip category={item.category} />
                      </td>
                      <td className="max-w-[28rem] px-3 py-2.5">
                        <div className="text-[var(--desk-text)]">{item.title}</div>
                        <div className="mt-0.5 line-clamp-2 text-xs text-[var(--desk-mist)]">
                          {item.summary || "—"}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-xs text-[var(--desk-mist)]">
                        {item.symbol || item.name ? (
                          <>
                            <div className="font-mono">{item.symbol || "—"}</div>
                            <div>{item.name || ""}</div>
                          </>
                        ) : (
                          item.region || "—"
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        <ImportanceDots value={item.importance} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <style>{`
        @keyframes desk-cal-in {
          from { opacity: 0; transform: translateY(3px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          tr[style], li[style] { animation: none !important; }
        }
      `}</style>
    </div>
  );
}

/**
 * 格式化为 YYYY-MM-DD。
 */
function formatDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * 生成从当月起连续 N 个月的下拉选项。
 */
function buildMonthOptions(from: Date, count: number): Array<{ key: string; label: string }> {
  const options: Array<{ key: string; label: string }> = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(from.getFullYear(), from.getMonth() + i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = i === 0 ? `${d.getFullYear()}年${d.getMonth() + 1}月（本月）` : `${d.getFullYear()}年${d.getMonth() + 1}月`;
    options.push({ key, label });
  }
  return options;
}

/**
 * 计算某月查询区间；本月从今天起，其余为整月。
 */
function monthRange(monthKey: string, today: Date): { start: string; end: string } {
  const [yRaw, mRaw] = monthKey.split("-");
  const year = Number(yRaw);
  const month = Number(mRaw);
  const monthStart = new Date(year, month - 1, 1);
  const monthEnd = new Date(year, month, 0);
  const todayKey = formatDateKey(today);
  const startKey = formatDateKey(monthStart);
  const endKey = formatDateKey(monthEnd);
  const start = startKey < todayKey ? todayKey : startKey;
  return { start, end: endKey };
}

function Empty({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--desk-line)] bg-[var(--desk-ink)] px-4 py-10 text-center">
      <p className="text-sm text-[var(--desk-text)]">{title}</p>
      <p className="mt-1 text-xs text-[var(--desk-mist)]">{hint}</p>
    </div>
  );
}

const inputClass =
  "min-w-[10rem] flex-1 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-1.5 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)] sm:max-w-[14rem]";

const selectClass =
  "rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-2.5 py-1.5 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)] disabled:opacity-60";

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "accent";
}) {
  const color =
    tone === "success"
      ? "text-[var(--success)]"
      : tone === "accent"
        ? "text-[var(--desk-accent)]"
        : "text-[var(--desk-text)]";
  return (
    <div className="rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-4 py-3">
      <div className="text-xs text-[var(--desk-mist)]">{label}</div>
      <div className={`mt-1 font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

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

function CategoryChip({ category }: { category: string }) {
  const color =
    category === "news"
      ? "accent"
      : category === "macro"
        ? "success"
        : category === "lockup" || category === "earnings"
          ? "danger"
          : "accent";
  return (
    <Chip size="sm" variant="soft" color={color}>
      {CATEGORY_LABEL[category] || category}
    </Chip>
  );
}

function ImportanceDots({ value }: { value: number }) {
  const n = Math.max(1, Math.min(5, Number(value) || 1));
  return (
    <div className="flex items-center gap-0.5" title={`重要度 ${n}/5`} aria-label={`重要度 ${n}`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={[
            "inline-block h-1.5 w-1.5 rounded-full",
            i < n ? "bg-[var(--desk-accent)]" : "bg-[var(--desk-line)]",
          ].join(" ")}
        />
      ))}
    </div>
  );
}
