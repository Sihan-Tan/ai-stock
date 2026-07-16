export type NavigationItem = {
  path: string;
  label: string;
  end?: boolean;
};

/**
 * Desk 工作台的完整一级导航配置。
 */
export const NAV: NavigationItem[] = [
  { path: "/", label: "总览", end: true },
  { path: "/market-sync", label: "行情同步" },
  { path: "/watchlist", label: "行情自选" },
  { path: "/sentiment", label: "打板情绪" },
  { path: "/lhb", label: "龙虎榜" },
  { path: "/calendar", label: "日历/停牌" },
  { path: "/strategies", label: "策略" },
  { path: "/factors", label: "因子/ML" },
  { path: "/paper", label: "模拟盘" },
  { path: "/risk", label: "实盘风控" },
  { path: "/alerts", label: "告警" },
  { path: "/ai", label: "投研 nanobot" },
  { path: "/morning", label: "晨会" },
  { path: "/review", label: "复盘" },
  { path: "/knowledge", label: "知识库" },
];
