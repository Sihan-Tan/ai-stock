import { Alert, Button, Chip, Popover, Switch } from "@heroui/react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
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
        <header className="sticky top-0 z-20 mb-5 flex items-start justify-between gap-4 border-b border-[var(--desk-line)] bg-[var(--desk-ink)]/95 py-3 backdrop-blur-sm">
          <h1 className="text-2xl font-semibold text-[var(--desk-accent)]">{title}</h1>
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
