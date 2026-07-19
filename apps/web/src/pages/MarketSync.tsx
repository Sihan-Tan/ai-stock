import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api, formatBeijingTime } from "../api";
import type { PageLogProps } from "./types";

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
  sync_sentiment_daily: "打板情绪",
  sync_lhb_daily: "龙虎榜",
  run_morning_preopen: "晨会开盘前",
  ingest_auction_snapshots: "竞价快照",
  run_morning_post_auction: "晨会竞价选拔",
};

/**
 * 行情同步：手动触发日历/证券列表/日线/回填/分钟任务，并轮询 Job 状态。
 */
export default function MarketSync({ setLog }: PageLogProps) {
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

  /**
   * 同步执行（情绪/龙虎榜等非 BackgroundTasks 接口）。
   * @param path API 路径
   * @param label 日志展示名
   */
  const runInline = async (path: string, label: string) => {
    setBusy(true);
    try {
      const res = await api<{ status?: string; skipped?: boolean; error?: string }>(path, {
        method: "POST",
      });
      if (res.skipped) setLog(`${label}：非交易日已跳过`);
      else if (res.status === "failed") setLog(`${label}失败：${res.error || "unknown"}`);
      else setLog(`${label}完成`);
      await loadJobs();
    } catch (e) {
      setLog(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="p-5 pb-3">
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle className="text-base text-[var(--desk-text)]">行情任务</CardTitle>
          <Chip color={jobs.some((job) => job.status === "running") ? "warning" : "success"} variant="soft">
            {jobs.some((job) => job.status === "running") ? "同步中" : "空闲"}
          </Chip>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-5 pt-2">
        <p className="text-sm leading-6 text-[var(--desk-mist)]">
          任务后台执行；有 running 时每 2 秒刷新进度。历史回填会把「最早日晚于配置起始日」的标的从{" "}
          <code>daily_start_date</code> 起按 example 方式（download + front/back）重拉。分钟同步仅在交易时段自动跑，盘后需手动触发。
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            isDisabled={busy}
            onPress={() => enqueue("/api/market/jobs/calendar-sync", "交易日历")}
          >
            同步日历
          </Button>
          <Button
            variant="secondary"
            isDisabled={busy}
            onPress={() => enqueue("/api/market/jobs/security-list", "证券列表")}
          >
            同步证券列表
          </Button>
          <Button
            variant="primary"
            isDisabled={busy}
            onPress={() => enqueue("/api/market/jobs/daily-sync", "日终日线")}
          >
            日终增量
          </Button>
          <Button
            variant="primary"
            isDisabled={busy}
            onPress={() => enqueue("/api/market/jobs/backfill", "历史回填")}
          >
            历史回填
          </Button>
          <Button
            variant="secondary"
            isDisabled={busy}
            onPress={() => enqueue("/api/market/jobs/minute-sync", "分钟同步")}
          >
            分钟同步
          </Button>
          <Button
            variant="secondary"
            isDisabled={busy}
            onPress={() => void runInline("/api/sentiment/jobs/sync", "打板情绪")}
          >
            同步情绪
          </Button>
          <Button
            variant="secondary"
            isDisabled={busy}
            onPress={() => void runInline("/api/lhb/jobs/sync", "龙虎榜")}
          >
            同步龙虎榜
          </Button>
          <Button variant="secondary" onPress={loadJobs}>
            刷新状态
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
          <thead className="border-b border-[var(--desk-line)] text-[var(--desk-mist)]">
            <tr>
              <th className="px-3 py-2 font-medium">ID</th>
              <th className="px-3 py-2 font-medium">任务</th>
              <th className="px-3 py-2 font-medium">状态</th>
              <th className="px-3 py-2 font-medium">已完成</th>
              <th className="px-3 py-2 font-medium">消息</th>
              <th className="px-3 py-2 font-medium">开始</th>
              <th className="px-3 py-2 font-medium">结束</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id} className="border-b border-[var(--desk-line)] last:border-0 hover:bg-[var(--desk-ink)]">
                <td className="px-3 py-3 font-mono">{j.id}</td>
                <td className="px-3 py-3">{JOB_LABELS[j.job_id] || j.job_id}</td>
                <td className="px-3 py-3 font-mono">{j.status}</td>
                <td className="px-3 py-3 font-mono">{j.symbols_done}</td>
                <td className="px-3 py-3 text-[var(--desk-mist)]">{j.error_summary || j.message || "—"}</td>
                <td className="px-3 py-3 font-mono text-[var(--desk-mist)]">{formatBeijingTime(j.started_at)}</td>
                <td className="px-3 py-3 font-mono text-[var(--desk-mist)]">{formatBeijingTime(j.finished_at)}</td>
              </tr>
            ))}
            {!jobs.length && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-[var(--desk-mist)]">
                  暂无任务记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </CardContent>
    </Card>
  );
}
