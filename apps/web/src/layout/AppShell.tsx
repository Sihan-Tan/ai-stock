import { Alert, Button, Chip, Input, Popover, Switch } from "@heroui/react";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api";
import {
  resolveSearchNavigation,
  type SearchHit,
} from "../stock/resolveSearchNavigation";
import { applyTheme, type ThemeId } from "../theme/theme";
import { NAV } from "./nav";

export type AppShellProps = {
  title: string;
  health: Record<string, unknown> | null;
  healthError: string | null;
  log: string;
  theme: ThemeId;
  onThemeChange: (theme: ThemeId) => void;
  children: ReactNode;
};

/**
 * 根据健康检查结果推导 Chip 颜色与文案。
 * @param health /health 响应
 * @param healthError API 请求错误
 */
function healthSummary(
  health: Record<string, unknown> | null,
  healthError: string | null
): {
  apiColor: "success" | "danger" | "default";
  apiLabel: string;
  dbColor: "success" | "warning" | "danger" | "default";
  dbLabel: string;
} {
  if (healthError) {
    return {
      apiColor: "danger",
      apiLabel: "API 不可达",
      dbColor: "default",
      dbLabel: "DB —",
    };
  }
  if (!health) {
    return {
      apiColor: "default",
      apiLabel: "API 检测中",
      dbColor: "default",
      dbLabel: "DB —",
    };
  }
  const dbOk = health.db === true;
  return {
    apiColor: "success",
    apiLabel: "API 正常",
    dbColor: dbOk ? "success" : "warning",
    dbLabel: dbOk ? "DB 正常" : "DB 不可达",
  };
}

type SearchResponse = { query: string; items: SearchHit[] };

/**
 * 渲染 Desk 工作台的导航、运行状态与路由内容壳层。
 * @param props 壳层展示及主题切换所需状态
 */
export function AppShell({
  title,
  health,
  healthError,
  log,
  theme,
  onThemeChange,
  children,
}: AppShellProps) {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHint, setSearchHint] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<SearchHit[]>([]);
  const [openSuggest, setOpenSuggest] = useState(false);
  const searchWrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const q = searchQuery.trim();
    if (!q) {
      setSuggestions([]);
      setOpenSuggest(false);
      return;
    }
    const timer = window.setTimeout(() => {
      api<SearchResponse>(
        `/api/market/stock/search?q=${encodeURIComponent(q)}&limit=6`
      )
        .then((res) => {
          setSuggestions(res.items || []);
          setOpenSuggest((res.items || []).length > 0);
        })
        .catch(() => {
          setSuggestions([]);
          setOpenSuggest(false);
        });
    }, 200);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    /** 点击搜索区域外关闭下拉。 */
    const onDocMouseDown = (event: MouseEvent) => {
      if (!searchWrapRef.current?.contains(event.target as Node)) {
        setOpenSuggest(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  /**
   * 跳转到股票详情并收起下拉。
   * @param symbol 标的代码
   * @param label 输入框展示文案
   */
  const goStock = (symbol: string, label?: string) => {
    setSearchHint(null);
    setOpenSuggest(false);
    if (label != null) setSearchQuery(label);
    navigate(`/stock/${encodeURIComponent(symbol)}`);
  };

  /** 提交顶部搜索：代码直达，否则取候选第一条。 */
  const handleSearchSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const target = resolveSearchNavigation(searchQuery, suggestions);
    if (target) {
      goStock(target);
      return;
    }
    setSearchHint("未找到匹配标的");
    setOpenSuggest(false);
  };

  const changeTheme = (isSelected: boolean) => {
    const nextTheme: ThemeId = isSelected ? "desk-light" : "desk-dark";
    applyTheme(nextTheme);
    onThemeChange(nextTheme);
  };

  const summary = healthSummary(health, healthError);
  const tradeMode = health?.trade_mode != null ? String(health.trade_mode) : null;
  const mlEngine = health?.ml_engine != null ? String(health.ml_engine) : null;
  const llmProvider = health?.llm_provider != null ? String(health.llm_provider) : null;

  return (
    <div className="grid min-h-screen grid-cols-[220px_1fr] bg-[var(--desk-ink)] text-[var(--desk-text)] max-md:grid-cols-1">
      <aside className="flex min-h-full flex-col border-r border-[var(--desk-line)] bg-[var(--desk-panel)] p-4 max-md:border-r-0 max-md:border-b">
        <div className="mb-6 text-lg font-semibold tracking-wide text-[var(--desk-accent)]">
          刻度<span className="text-[var(--desk-mist)]">·</span>Desk
        </div>
        <nav aria-label="主导航" className="flex flex-1 flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) =>
                [
                  "rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-[var(--desk-accent)] text-[var(--desk-panel)] font-semibold"
                    : "text-[var(--desk-mist)] hover:bg-[var(--desk-line)] hover:text-[var(--desk-text)]",
                ].join(" ")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-6 flex items-center justify-between border-t border-[var(--desk-line)] pt-4">
          <span className="text-sm text-[var(--desk-mist)]">浅色主题</span>
          <Switch
            aria-label="切换浅色主题"
            isSelected={theme === "desk-light"}
            onChange={changeTheme}
          />
        </div>
      </aside>
      <main className="min-w-0 p-6 max-md:p-4">
        <header className="sticky top-0 z-20 mb-5 flex flex-wrap items-start justify-between gap-4 border-b border-[var(--desk-line)] bg-[var(--desk-ink)]/95 py-3 backdrop-blur-sm">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold text-[var(--desk-accent)]">{title}</h1>
            <div ref={searchWrapRef} className="relative">
              <form
                className="flex flex-wrap items-center gap-2"
                onSubmit={handleSearchSubmit}
              >
                <Input
                  aria-label="搜索股票代码或名称"
                  className="w-44"
                  placeholder="代码 / 名称 / 拼音"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    if (searchHint) setSearchHint(null);
                  }}
                  onFocus={() => {
                    if (suggestions.length > 0) setOpenSuggest(true);
                  }}
                />
                <Button size="sm" type="submit" variant="secondary">
                  搜索
                </Button>
                {searchHint && (
                  <span className="text-xs text-[var(--danger)]">{searchHint}</span>
                )}
              </form>
              {openSuggest && suggestions.length > 0 && (
                <ul
                  className="absolute left-0 top-full z-30 mt-1 w-72 overflow-hidden rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] shadow-lg"
                  role="listbox"
                >
                  {suggestions.map((item) => (
                    <li key={item.symbol}>
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-[var(--desk-line)]"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() =>
                          goStock(item.symbol, `${item.symbol} ${item.name}`)
                        }
                      >
                        <span className="font-mono text-xs text-[var(--desk-mist)]">
                          {item.symbol}
                        </span>
                        <span className="truncate text-[var(--desk-text)]">
                          {item.name}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <Chip color={summary.apiColor} variant="soft">
              {summary.apiLabel}
            </Chip>
            <Chip color={summary.dbColor} variant="soft">
              {summary.dbLabel}
            </Chip>
            {tradeMode && (
              <Chip color="accent" variant="soft">
                mode · {tradeMode}
              </Chip>
            )}
            {mlEngine && (
              <Chip color="accent" variant="soft">
                ml · {mlEngine}
              </Chip>
            )}
            {llmProvider && (
              <Chip color="accent" variant="soft">
                llm · {llmProvider}
              </Chip>
            )}
            <Popover>
              <Popover.Trigger>
                <Button size="sm" variant="secondary">
                  健康详情
                </Button>
              </Popover.Trigger>
              <Popover.Content className="max-w-md border border-[var(--desk-line)] bg-[var(--desk-panel)] p-0">
                <Popover.Dialog className="p-4 outline-none">
                  <Popover.Heading className="mb-2 text-sm font-semibold text-[var(--desk-text)]">
                    API 健康
                  </Popover.Heading>
                  {healthError ? (
                    <p className="text-sm text-[var(--danger)]">{healthError}</p>
                  ) : (
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md bg-[var(--desk-ink)] p-3 font-mono text-xs text-[var(--desk-mist)]">
                      {health ? JSON.stringify(health, null, 2) : "检测中…"}
                    </pre>
                  )}
                  <p className="mt-3 border-t border-[var(--desk-line)] pt-2 text-xs text-[var(--desk-mist)]">
                    日志：{log}
                  </p>
                </Popover.Dialog>
              </Popover.Content>
            </Popover>
          </div>
        </header>

        {(healthError || (!healthError && health?.db === false)) && (
          <div className="mb-5 space-y-3">
            {healthError && (
              <Alert color="danger" title="API 不可达">
                {healthError}
              </Alert>
            )}
            {!healthError && health?.db === false && (
              <Alert color="warning" title="数据库不可达">
                API 已启动但读写会失败。请检查 Postgres（DATABASE_URL）是否已启动。
              </Alert>
            )}
          </div>
        )}

        <div>{children}</div>
      </main>
    </div>
  );
}
