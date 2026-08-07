import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";
import {
  EmptyPickNotice,
  EmptyRow,
  asofDateInputClass,
  formatPct,
  formatPrice,
  formatScore,
  formatStrategyLabel,
  PrimaryAction,
  ResearchPicksPanel,
  type ResearchPickRow,
  SecondaryAction,
  SessionBrief,
  SessionHero,
  SessionPager,
  SessionPanel,
  SessionTable,
  StrategyChip,
  tdClass,
  thClass,
  trClickClass,
  usePagedItems,
} from "./sessionPick/shared";

type ClosingLatest = {
  asof: string;
  briefs: Record<string, { content?: string; stage?: string }>;
  stocks: Array<{
    symbol?: string;
    code?: string;
    name?: string;
    strategy_id?: string;
    pct_chg?: number;
    score?: number;
    price?: number;
    last_close?: number;
  }>;
  research_picks?: ResearchPickRow[];
};

type ClosingStrategy = {
  id: string;
  name: string;
  closing?: boolean;
  status?: string;
};

/**
 * 尾盘选股：策略多选、跑选、命中列表。
 * @param props 页面日志写入方法
 */
export default function Closing({ setLog }: PageLogProps) {
  const [data, setData] = useState<ClosingLatest | null>(null);
  /** YYYY-MM-DD；空=尚未同步，默认业务日由后端解析 */
  const [asof, setAsof] = useState("");
  /** 用户是否主动改过日期（用于区分「尚未运行」与「该日暂无数据」） */
  const [asofPicked, setAsofPicked] = useState(false);
  const [strategies, setStrategies] = useState<ClosingStrategy[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);
  const strategiesInitialized = useRef(false);

  /**
   * 加载尾盘结果；显式选日或已回看时走 history，避免非交易日回退。
   * @param nextAsof 显式业务日；缺省用当前 asof 状态
   */
  const loadLatest = async (nextAsof?: string) => {
    const q = nextAsof || asof;
    const useHistory = (nextAsof != null && nextAsof !== "") || asofPicked;
    let url: string;
    if (useHistory && q) {
      url = `/api/closing/history?asof=${encodeURIComponent(q)}`;
    } else if (q) {
      url = `/api/closing/latest?asof=${encodeURIComponent(q)}`;
    } else {
      url = "/api/closing/latest";
    }
    try {
      const latest = await api<ClosingLatest>(url);
      setData(latest);
      if (latest.asof) setAsof(latest.asof);
    } catch (error) {
      setLog(String(error));
    }
  };

  /**
   * 加载策略列表；首次默认勾选 closing 角色策略。
   */
  const loadStrategies = () =>
    api<ClosingStrategy[]>("/api/closing/strategies")
      .then((list) => {
        setStrategies(list);
        if (!strategiesInitialized.current) {
          setSelectedIds(list.filter((item) => item.closing).map((item) => item.id));
          strategiesInitialized.current = true;
        }
      })
      .catch((error) => setLog(String(error)));

  /**
   * 刷新 latest 与策略列表。
   */
  const refresh = async () => {
    await Promise.all([loadLatest(), loadStrategies()]);
  };

  useEffect(() => {
    void refresh();
  }, []);

  /**
   * 切换策略勾选。
   * @param strategyId 策略 ID
   * @param checked 是否选中
   */
  const toggleStrategy = (strategyId: string, checked: boolean) => {
    setSelectedIds((prev) =>
      checked ? [...new Set([...prev, strategyId])] : prev.filter((id) => id !== strategyId)
    );
  };

  /**
   * 立即跑尾盘选股。空勾选时后端按全部 closing 策略执行。
   */
  const runNow = async () => {
    setBusy(true);
    try {
      const hasTagged = strategies.some((item) => item.closing);
      if (!selectedIds.length && !hasTagged) {
        setLog("没有可跑的策略：请先在本页勾选策略，或到策略页标记「尾盘」后再跑");
        return;
      }
      const report = await api<{ stocks?: unknown[]; content?: string; asof?: string }>(
        "/api/closing/run",
        {
          method: "POST",
          body: JSON.stringify({ strategy_ids: selectedIds }),
        }
      );
      await loadLatest(report.asof || undefined);
      const n = Array.isArray(report.stocks) ? report.stocks.length : 0;
      const asofNote = report.asof ? `（${report.asof}）` : "";
      setLog(
        n > 0
          ? `尾盘选股完成${asofNote}：命中 ${n} 只`
          : `尾盘选股完成${asofNote}：未选出符合条件的股票。${report.content ? "详见场次摘要。" : ""}`
      );
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 将当日尾盘命中写入自选；有勾选时仅绑定对应策略。
   */
  const bindWatchlist = async () => {
    setBusy(true);
    try {
      const result = await api<{ count: number; added: string[] }>("/api/closing/bind", {
        method: "POST",
        body: JSON.stringify({
          asof: asof || data?.asof || undefined,
          limit: 20,
          strategy_ids: selectedIds.length ? selectedIds : undefined,
        }),
      });
      setLog(`已写入自选 ${result.count} 只：${(result.added || []).slice(0, 8).join(", ")}`);
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 对原筛选候选跑投研精选并刷新 latest。
   */
  const runResearchRefine = async () => {
    setBusy(true);
    try {
      const day = asof || data?.asof || undefined;
      const report = await api<{
        picks?: ResearchPickRow[];
        candidates_evaluated?: number;
        errors?: string[];
      }>("/api/closing/research-refine", {
        method: "POST",
        body: JSON.stringify({ asof: day }),
      });
      await loadLatest(day);
      const errs = report.errors ?? [];
      if (errs.includes("llm_api_key_missing")) {
        setLog("投研精选失败：未配置 LLM API Key，请到「设置 → LLM」填写后再试。");
        return;
      }
      const hardErr = errs.find(
        (e) =>
          e.includes("LLM ") ||
          e.includes("Error code") ||
          e.includes("未解析到评分") ||
          e.includes("BadRequest")
      );
      if (hardErr && !(report.picks?.length)) {
        setLog(`投研精选失败：${hardErr}`);
        return;
      }
      const n = report.picks?.length ?? 0;
      const errNote = errs.length ? `；跳过 ${errs.length} 条` : "";
      setLog(
        `投研精选完成：入选 ${n} 只（评估 ${report.candidates_evaluated ?? "—"} 只候选）${errNote}`
      );
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  const brief = data?.briefs?.closing;
  const allStocks = data?.stocks ?? [];
  const researchPicks = data?.research_picks ?? [];
  const displayStocks =
    selectedIds.length > 0
      ? allStocks.filter(
          (stock) => stock.strategy_id != null && selectedIds.includes(stock.strategy_id)
        )
      : allStocks;
  const stockPage = usePagedItems(displayStocks);
  const taggedCount = strategies.filter((s) => s.closing).length;
  const hasRun = Boolean(brief?.content);
  const filteredEmpty = selectedIds.length > 0 && allStocks.length > 0 && displayStocks.length === 0;
  const noPickAfterRun = hasRun && allStocks.length === 0;
  const emptyDay =
    asofPicked && !hasRun && allStocks.length === 0 && researchPicks.length === 0;

  return (
    <div className="space-y-4">
      <SessionHero
        kind="closing"
        asof={data?.asof || asof || undefined}
        busy={busy}
        hasRun={hasRun}
        metrics={[
          { label: "命中", value: displayStocks.length },
          { label: "已选策略", value: selectedIds.length || "全部" },
          { label: "已标记", value: taggedCount },
        ]}
        actions={
          <>
            <SecondaryAction isDisabled={busy} onPress={() => void refresh()}>
              刷新
            </SecondaryAction>
            <SecondaryAction
              isDisabled={busy || !displayStocks.length}
              onPress={() => void bindWatchlist()}
            >
              进自选
            </SecondaryAction>
            <input
              type="date"
              className={asofDateInputClass}
              value={asof || ""}
              disabled={busy}
              onChange={(e) => {
                const v = e.target.value;
                setAsof(v);
                setAsofPicked(true);
                void loadLatest(v);
              }}
              aria-label="选择回看日期"
            />
            <SecondaryAction
              isDisabled={busy || !allStocks.length}
              onPress={() => void runResearchRefine()}
            >
              投研精选
            </SecondaryAction>
            <PrimaryAction
              isDisabled={busy || !strategies.length}
              onPress={() => void runNow()}
            >
              立即跑
            </PrimaryAction>
          </>
        }
      />

      {emptyDay && (
        <EmptyPickNotice
          title="该日暂无数据"
          tip="所选日期尚无尾盘摘要或命中结果。可换一天回看，或点「立即跑」生成当日数据。"
        />
      )}

      {!hasRun && !emptyDay && (
        <EmptyPickNotice
          title="尚未运行尾盘选股"
          tip="先在策略页勾选「尾盘」，再点「立即跑」。若跑完仍无命中，页面会给出明确提示。"
        />
      )}

      <SessionPanel title="场次摘要" hint="定时约 14:40 自动跑；也可点右上角「立即跑」。">
        <SessionBrief
          title="尾盘"
          content={brief?.content}
          emptyHint={
            emptyDay
              ? "该日暂无数据。"
              : "暂无摘要。先在策略页标记「尾盘」，再点「立即跑」。"
          }
        />
      </SessionPanel>

      <SessionPanel
        title="参与策略"
        hint="勾选决定下方个股筛选与重跑范围；全部取消时按已标记尾盘策略执行。"
        action={
          <div className="flex gap-2">
            <SecondaryAction
              isDisabled={busy || !strategies.some((s) => s.closing)}
              onPress={() =>
                setSelectedIds(strategies.filter((s) => s.closing).map((s) => s.id))
              }
            >
              仅已标记
            </SecondaryAction>
            <SecondaryAction
              isDisabled={busy || !strategies.length}
              onPress={() => setSelectedIds(strategies.map((s) => s.id))}
            >
              全选
            </SecondaryAction>
            <SecondaryAction
              isDisabled={busy || !selectedIds.length}
              onPress={() => setSelectedIds([])}
            >
              清空
            </SecondaryAction>
          </div>
        }
      >
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {strategies.map((strategy) => (
            <StrategyChip
              key={strategy.id}
              id={strategy.id}
              name={strategy.name}
              selected={selectedIds.includes(strategy.id)}
              tagged={strategy.closing}
              onToggle={toggleStrategy}
            />
          ))}
        </div>
        {!strategies.length && (
          <p className="text-sm text-[var(--desk-mist)]">暂无可用策略。</p>
        )}
      </SessionPanel>

      {filteredEmpty && (
        <EmptyPickNotice
          title="当前勾选策略下无命中"
          tip={`当日共有 ${allStocks.length} 条命中，但不在当前勾选范围内。请调整上方策略勾选，或点「仅已标记 / 清空」后再看下方个股。`}
        />
      )}

      {noPickAfterRun && (
        <EmptyPickNotice
          title="本次未选出符合条件的股票"
          tip="尾盘选股已跑完，参与策略均未打出买点。可放宽规则条件、确认行情日线是否齐全，或换一组策略后再跑。"
        />
      )}

      <SessionPanel
        title="命中个股"
        hint="有勾选时仅展示所选策略结果；点击行打开详情。"
        action={
          <PrimaryAction
            isDisabled={busy || !displayStocks.length}
            onPress={() => void bindWatchlist()}
          >
            一键进自选
          </PrimaryAction>
        }
      >
        <SessionTable>
          <thead>
            <tr>
              <th className={thClass}>#</th>
              <th className={thClass}>代码</th>
              <th className={thClass}>名称</th>
              <th className={thClass}>现价</th>
              <th className={thClass}>策略</th>
              <th className={thClass}>涨跌幅</th>
              <th className={thClass}>得分</th>
            </tr>
          </thead>
          <tbody>
            {stockPage.slice.map((stock, index) => {
              const symbol = stock.symbol || stock.code || "";
              const rowNo = (stockPage.page - 1) * stockPage.pageSize + index + 1;
              const price = stock.price ?? stock.last_close;
              return (
                <tr
                  key={`${symbol}-${stock.strategy_id || ""}`}
                  className={trClickClass}
                  onClick={() => symbol && setDrawerSymbol(symbol)}
                >
                  <td className={`${tdClass} font-mono text-[var(--desk-mist)]`}>{rowNo}</td>
                  <td className={`${tdClass} font-mono text-[var(--desk-text)]`}>
                    {symbol || "—"}
                  </td>
                  <td className={tdClass}>{stock.name || "—"}</td>
                  <td className={`${tdClass} font-mono`}>{formatPrice(price)}</td>
                  <td className={`${tdClass} text-xs`}>
                    {formatStrategyLabel(stock.strategy_id)}
                  </td>
                  <td className={`${tdClass} font-mono ${chgToneClass(stock.pct_chg)}`}>
                    {formatPct(stock.pct_chg)}
                  </td>
                  <td className={`${tdClass} font-mono`}>{formatScore(stock.score)}</td>
                </tr>
              );
            })}
            {!displayStocks.length && (
              <EmptyRow
                colSpan={7}
                message={
                  emptyDay
                    ? "该日暂无数据。"
                    : filteredEmpty
                      ? "当前勾选策略下无命中，请调整勾选。"
                      : noPickAfterRun
                        ? "本次未选出符合条件的股票。"
                        : "暂无命中。标记尾盘策略后点击「立即跑」。"
                }
              />
            )}
          </tbody>
        </SessionTable>
        <SessionPager
          page={stockPage.page}
          pageSize={stockPage.pageSize}
          total={stockPage.total}
          onPageChange={stockPage.setPage}
        />
      </SessionPanel>

      <ResearchPicksPanel
        picks={researchPicks}
        busy={busy}
        onRun={() => void runResearchRefine()}
        emptyHint={
          emptyDay
            ? "该日暂无数据。"
            : allStocks.length
              ? "暂无投研精选。点击「投研精选」对当前命中个股打分。"
              : "暂无投研精选。请先完成尾盘选拔后再运行。"
        }
        onRowClick={(symbol) => setDrawerSymbol(symbol)}
      />

      <StockDetailDrawer
        open={drawerSymbol !== null}
        symbol={drawerSymbol ?? ""}
        onClose={() => setDrawerSymbol(null)}
      />
    </div>
  );
}
