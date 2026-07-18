import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { AppShell } from "./layout/AppShell";
import { NAV } from "./layout/nav";
import Alerts from "./pages/Alerts";
import Calendar from "./pages/Calendar";
import Factors from "./pages/Factors";
import Knowledge from "./pages/Knowledge";
import Lhb from "./pages/Lhb";
import MarketSync from "./pages/MarketSync";
import Morning from "./pages/Morning";
import Paper from "./pages/Paper";
import Research from "./pages/Research";
import Review from "./pages/Review";
import Risk from "./pages/Risk";
import Sentiment from "./pages/Sentiment";
import Settings from "./pages/Settings";
import StockDetail from "./pages/StockDetail";
import Backtest from "./pages/Backtest";
import Strategies from "./pages/Strategies";
import Watchlist from "./pages/Watchlist";
import { readStoredTheme } from "./theme/theme";

/**
 * 工作台壳层：负责路由、健康检查与主题状态。
 */
export default function App() {
  const location = useLocation();
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [log, setLog] = useState("就绪");
  const [healthError, setHealthError] = useState<string | null>(null);
  const [theme, setTheme] = useState(readStoredTheme);

  useEffect(() => {
    /** 拉取 /health；数据库不可达时仅展示横幅，不阻塞页面。 */
    const refreshHealth = () =>
      api<Record<string, unknown>>("/health")
        .then((result) => {
          setHealth(result);
          setHealthError(null);
        })
        .catch((error) => setHealthError(String(error)));

    refreshHealth();
    const timer = window.setInterval(refreshHealth, 10000);
    return () => window.clearInterval(timer);
  }, []);

  const title = useMemo(
    () =>
      location.pathname.startsWith("/stock/")
        ? "股票详情"
        : (NAV.find((item) => location.pathname === item.path)?.label ?? ""),
    [location.pathname]
  );

  return (
    <AppShell
      title={title}
      health={health}
      healthError={healthError}
      log={log}
      theme={theme}
      onThemeChange={setTheme}
    >
      <Routes>
        <Route path="/" element={<Navigate to="/monitor" replace />} />
        <Route path="/paper" element={<Navigate to="/monitor" replace />} />
        <Route path="/monitor" element={<Paper setLog={setLog} />} />
        <Route path="/market-sync" element={<MarketSync setLog={setLog} />} />
        <Route path="/watchlist" element={<Watchlist setLog={setLog} />} />
        <Route path="/sentiment" element={<Sentiment setLog={setLog} />} />
        <Route path="/lhb" element={<Lhb setLog={setLog} />} />
        <Route path="/calendar" element={<Calendar setLog={setLog} />} />
        <Route path="/strategies" element={<Strategies setLog={setLog} />} />
        <Route path="/backtest" element={<Backtest setLog={setLog} />} />
        <Route path="/factors" element={<Factors setLog={setLog} />} />
        <Route path="/risk" element={<Risk setLog={setLog} />} />
        <Route path="/alerts" element={<Alerts setLog={setLog} />} />
        <Route path="/ai" element={<Research setLog={setLog} />} />
        <Route path="/morning" element={<Morning setLog={setLog} />} />
        <Route path="/review" element={<Review setLog={setLog} />} />
        <Route path="/knowledge" element={<Knowledge setLog={setLog} />} />
        <Route path="/settings" element={<Settings setLog={setLog} />} />
        <Route path="/stock/:symbol" element={<StockDetail />} />
        <Route path="*" element={<Navigate to="/monitor" replace />} />
      </Routes>
    </AppShell>
  );
}
