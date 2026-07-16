import { Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

type CalendarDay = { date: string; is_open: boolean };

/**
 * 展示本月交易日与停牌提醒。
 * @param props 页面日志写入方法
 */
export default function Calendar({ setLog }: PageLogProps) {
  const [month, setMonth] = useState<CalendarDay[]>([]);
  const [suspensions, setSuspensions] = useState<unknown[]>([]);

  useEffect(() => {
    const now = new Date();
    Promise.all([
      api<CalendarDay[]>(`/api/calendar/month?year=${now.getFullYear()}&month=${now.getMonth() + 1}`),
      api<unknown[]>("/api/calendar/suspensions"),
    ])
      .then(([calendar, suspended]) => {
        setMonth(calendar);
        setSuspensions(suspended);
      })
      .catch((error) => setLog(String(error)));
  }, []);

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex flex-wrap items-center gap-3 p-5 pb-3">
          <CardTitle className="text-base text-[var(--desk-text)]">本月交易日</CardTitle>
          <Chip variant="soft" color="success">{month.filter((day) => day.is_open).length} 天</Chip>
        </CardHeader>
        <CardContent className="p-5 pt-2 text-sm text-[var(--desk-mist)]">
          {month.slice(0, 10).map((day) => day.date).join(" · ")} {month.length > 10 ? "…" : ""}
        </CardContent>
      </Card>
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="p-5 pb-3"><CardTitle className="text-base text-[var(--desk-text)]">停牌提醒</CardTitle></CardHeader>
        <CardContent className="p-5 pt-2">
          <pre className="overflow-x-auto rounded-lg bg-[var(--desk-ink)] p-4 text-xs text-[var(--desk-mist)]">{JSON.stringify(suspensions, null, 2)}</pre>
        </CardContent>
      </Card>
    </div>
  );
}
