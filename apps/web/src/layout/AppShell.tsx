import { Alert, Chip, Switch } from "@heroui/react";
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

  return (
    <div className="grid min-h-screen grid-cols-[220px_1fr] bg-[var(--desk-bg)] text-[var(--desk-text)] max-md:grid-cols-1">
      <aside className="flex min-h-full flex-col border-r border-[var(--desk-line)] bg-[var(--desk-panel)] p-4 max-md:border-r-0 max-md:border-b">
        <div className="mb-6 text-lg font-semibold tracking-wide text-[var(--desk-accent)]">
          刻度<span className="text-[var(--desk-text-muted)]">·</span>Desk
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
                    : "text-[var(--desk-text-muted)] hover:bg-[var(--desk-panel-strong)] hover:text-[var(--desk-text)]",
                ].join(" ")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-6 flex items-center justify-between border-t border-[var(--desk-line)] pt-4">
          <span className="text-sm text-[var(--desk-text-muted)]">浅色主题</span>
          <Switch
            aria-label="切换浅色主题"
            isSelected={theme === "desk-light"}
            onChange={changeTheme}
          />
        </div>
      </aside>
      <main className="min-w-0 p-6 max-md:p-4">
        <header className="mb-5">
          <h1 className="text-2xl font-semibold text-[var(--desk-accent)]">{title}</h1>
        </header>
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
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-panel)] p-3">
            <Chip color={health?.db === true ? "success" : "warning"} variant="soft">
              API 健康
            </Chip>
            <span className="break-all font-mono text-sm text-[var(--desk-text-muted)]">
              {health ? JSON.stringify(health) : "检测中…"}
            </span>
          </div>
        </div>
        <div>{children}</div>
        <p className="mt-6 border-t border-[var(--desk-line)] pt-3 text-sm text-[var(--desk-text-muted)]">
          {log}
        </p>
      </main>
    </div>
  );
}
