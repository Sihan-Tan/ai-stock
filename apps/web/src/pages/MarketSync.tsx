import { useEffect, useState } from "react";
import { api, formatBeijingTime } from "../api";

type JobRun = {
  id: number;
  job_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  symbols_done: number;
  error_summary: string;
  message: string;
};

const JOB_LABELS: Record<string, string> = {
  sync_trade_calendar: "交易日历",
  sync_security_list: "证券列表",
  ingest_daily_incremental: "日终日线",
  backfill_daily_chunks: "历史回填",
  ingest_minute_watch: "分钟同步",
};

/**
 * 行情同步：手动触发日历/证券列表/日线/回填/分钟任务，并轮询 Job 状态。
 */
export default function MarketSync({ setLog }: { setLog: (s: string) => void }) {
  const [jobs, setJobs] = useState<JobRun[]>([]);
  const [busy, setBusy] = useState(false);

  const loadJobs = () =>
    api<JobRun[]>("/api/market/jobs/status?limit=30")
      .then(setJobs)
      .catch((e) => setLog(String(e)));

  useEffect(() => {
    loadJobs();
  }, []);

  useEffect(() => {
    const running = jobs.some((j) => j.status === "running");
    if (!running) return;
    const t = window.setInterval(() => {
      loadJobs();
    }, 2000);
    return () => window.clearInterval(t);
  }, [jobs]);

  /**
   * 入队行情 Job。
   * @param path API 路径
   * @param label 日志展示名
   */
  const enqueue = async (path: string, label: string) => {
    setBusy(true);
    try {
      const res = await api<{ run_id: number; status: string }>(path, { method: "POST" });
      setLog(`${label} 已入队 #${res.run_id}`);
      await loadJobs();
    } catch (e) {
      setLog(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div className="card">
        <p className="muted">
          任务后台执行；有 running 时每 2 秒刷新进度。历史回填会把「最早日晚于配置起始日」的标的从{" "}
          <code>daily_start_date</code> 起按 example 方式（download + front/back）重拉。分钟同步仅在交易时段自动跑，盘后需手动触发。
        </p>
        <div className="row">
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => enqueue("/api/market/jobs/calendar-sync", "交易日历")}
          >
            同步日历
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => enqueue("/api/market/jobs/security-list", "证券列表")}
          >
            同步证券列表
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => enqueue("/api/market/jobs/daily-sync", "日终日线")}
          >
            日终增量
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => enqueue("/api/market/jobs/backfill", "历史回填")}
          >
            历史回填
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => enqueue("/api/market/jobs/minute-sync", "分钟同步")}
          >
            分钟同步
          </button>
          <button type="button" className="btn" onClick={() => loadJobs()}>
            刷新状态
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>任务</th>
              <th>状态</th>
              <th>已完成</th>
              <th>消息</th>
              <th>开始(北京)</th>
              <th>结束(北京)</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="mono">{j.id}</td>
                <td>{JOB_LABELS[j.job_id] || j.job_id}</td>
                <td className="mono">{j.status}</td>
                <td className="mono">{j.symbols_done}</td>
                <td className="muted">{j.error_summary || j.message || "—"}</td>
                <td className="mono muted">{formatBeijingTime(j.started_at)}</td>
                <td className="mono muted">{formatBeijingTime(j.finished_at)}</td>
              </tr>
            ))}
            {!jobs.length && (
              <tr>
                <td colSpan={7} className="muted">
                  暂无任务记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
