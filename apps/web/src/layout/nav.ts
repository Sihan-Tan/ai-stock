export type NavigationItem = {
  path: string;
  label: string;
  end?: boolean;
};

/**
 * Desk 工作台的完整一级导航配置。
 */
export const NAV: NavigationItem[] = [
  { path: "/monitor", label: "实盘监控", end: true },
  { path: "/watchlist", label: "行情自选" },
  { path: "/sentiment", label: "打板情绪" },
  { path: "/lhb", label: "龙虎榜" },
  { path: "/calendar", label: "交易日历" },
  { path: "/strategies", label: "策略" },
  { path: "/backtest", label: "回测" },
  { path: "/factors", label: "因子/ML" },
  { path: "/alerts", label: "告警" },
  { path: "/ai", label: "投研 nanobot" },
  { path: "/morning", label: "晨会" },
  { path: "/market-sync", label: "行情同步" },
  { path: "/review", label: "复盘" },
  { path: "/knowledge", label: "知识库" },
  { path: "/settings", label: "设置" },
];
