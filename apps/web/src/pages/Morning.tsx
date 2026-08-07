import { useEffect, useState } from "react";
import { api } from "../api";
import { StockDetailDrawer } from "../stock/StockDetailDrawer";
import { chgToneClass } from "../ui/chgTone";
import type { PageLogProps } from "./types";
import {
  EmptyPickNotice,
  EmptyRow,
  asofDateInputClass,
  formatCompact,
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
  tdClass,
  thClass,
  trClickClass,
  usePagedItems,
} from "./sessionPick/shared";

type MorningLatest = {
  asof: string;
  briefs: Record<string, { content?: string; stage?: string }>;
  boards: Array<{
    board?: string;
    code?: string;
    name?: string;
    avg_pct?: number;
    count?: number;
    score?: number;
    strategy_id?: string;
  }>;
  stocks: Array<{
    symbol?: string;
    code?: string;
    name?: string;
    auction_pct?: number;
    auction_amount?: number;
    price?: number;
    board?: string;
    score?: number;
    strategy_id?: string;
  }>;
  research_picks?: ResearchPickRow[];
};

/**
 * 早盘选股：开盘前摘要与竞价强势选拔。
 * @param props 页面日志写入方法
 */
export default function Morning({ setLog }: PageLogProps) {
  const [data, setData] = useState<MorningLatest | null>(null);
  /** YYYY-MM-DD；空=尚未同步，默认业务日由后端解析 */
  const [asof, setAsof] = useState("");
  /** 用户是否主动改过日期（用于区分「尚未运行」与「该日暂无数据」） */
  const [asofPicked, setAsofPicked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [drawerSymbol, setDrawerSymbol] = useState<string | null>(null);
  const [briefTab, setBriefTab] = useState<"preopen" | "post_auction">("post_auction");

  /**
   * 加载早盘结果；可指定回看日。
   * @param nextAsof 显式业务日；缺省用当前 asof 状态
   */
  const load = async (nextAsof?: string) => {
    const q = nextAsof || asof;
    const url = q
      ? `/api/morning/latest?asof=${encodeURIComponent(q)}`
      : "/api/morning/latest";
    try {
      const latest = await api<MorningLatest>(url);
      setData(latest);
      if (latest.asof) setAsof(latest.asof);
    } catch (error) {
      setLog(String(error));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  /**
   * 运行开盘前 + 竞价选拔。
   */
  const runAll = async () => {
    setBusy(true);
    try {
      await api("/api/morning/preopen", { method: "POST" });
      await api("/api/morning/post-auction", { method: "POST" });
      const latest = await api<MorningLatest>("/api/morning/latest");
      setData(latest);
      if (latest.asof) setAsof(latest.asof);
      const n = latest.stocks?.length ?? 0;
      setLog(
        n > 0
          ? `早盘选股完成：强势个股 ${n} 只${latest.asof ? `（${latest.asof}）` : ""}`
          : `早盘选股完成：未选出符合条件的个股${latest.asof ? `（${latest.asof}）` : ""}`
      );
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 仅重跑竞价选拔。
   */
  const runAuction = async () => {
    setBusy(true);
    try {
      await api("/api/morning/post-auction", { method: "POST" });
      const latest = await api<MorningLatest>("/api/morning/latest");
      setData(latest);
      if (latest.asof) setAsof(latest.asof);
      setBriefTab("post_auction");
      const n = latest.stocks?.length ?? 0;
      setLog(
        n > 0 ? `竞价选拔完成：强势个股 ${n} 只` : "竞价选拔完成：未选出符合条件的个股"
      );
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  /**
   * 将当日强势个股写入自选。
   */
  const bindWatchlist = async () => {
    setBusy(true);
    try {
      const result = await api<{ count: number; added: string[] }>("/api/morning/bind", {
        method: "POST",
        body: JSON.stringify({ asof: asof || data?.asof || undefined, limit: 20 }),
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
      }>("/api/morning/research-refine", {
        method: "POST",
        body: JSON.stringify({ asof: day }),
      });
      await load(day);
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

  const pre = data?.briefs?.preopen;
  const post = data?.briefs?.post_auction;
  const boards = data?.boards ?? [];
  const stocks = data?.stocks ?? [];
  const researchPicks = data?.research_picks ?? [];
  const stockPage = usePagedItems(stocks);
  const activeBrief = briefTab === "preopen" ? pre : post;
  const hasRun = Boolean(pre?.content || post?.content);
  const noStockPick = hasRun && stocks.length === 0;
  const emptyDay =
    asofPicked && !hasRun && stocks.length === 0 && researchPicks.length === 0;

  return (
    <div className="space-y-4">
      <SessionHero
        kind="morning"
        asof={data?.asof || asof || undefined}
        busy={busy}
        hasRun={hasRun}
        metrics={[
          { label: "强势板块", value: boards.length },
          { label: "强势个股", value: stocks.length },
        ]}
        actions={
          <>
            <SecondaryAction isDisabled={busy} onPress={() => void load()}>
              刷新
            </SecondaryAction>
            <SecondaryAction isDisabled={busy} onPress={() => void runAuction()}>
              重跑竞价
            </SecondaryAction>
            <SecondaryAction
              isDisabled={busy || !stocks.length}
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
                void load(v);
              }}
              aria-label="选择回看日期"
            />
            <SecondaryAction
              isDisabled={busy || !stocks.length}
              onPress={() => void runResearchRefine()}
            >
              投研精选
            </SecondaryAction>
            <PrimaryAction isDisabled={busy} onPress={() => void runAll()}>
              运行早盘
            </PrimaryAction>
          </>
        }
      />

      {emptyDay && (
        <EmptyPickNotice
          title="该日暂无数据"
          tip="所选日期尚无早盘摘要或选拔结果。可换一天回看，或点「运行早盘」生成当日数据。"
        />
      )}

      {noStockPick && (
        <EmptyPickNotice
          title="本次未选出符合条件的个股"
          tip="竞价选拔已跑完，但在市宇宙内没有竞价上涨标的入围。可检查证券元数据/竞价快照是否齐全，或稍后再重跑。"
        />
      )}

      {!hasRun && !emptyDay && (
        <EmptyPickNotice
          title="尚未运行早盘选股"
          tip="点击右上角「运行早盘」生成开盘前摘要与竞价强势名单；若运行后仍无个股，页面会再次提示。"
        />
      )}

      <SessionPanel
        title="场次摘要"
        hint="开盘前看情绪与日历；竞价后看强势板块与个股打分。"
        action={
          <div className="flex gap-1 rounded-lg border border-[var(--desk-line)] p-0.5">
            {(
              [
                { key: "preopen" as const, label: "开盘前" },
                { key: "post_auction" as const, label: "竞价" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setBriefTab(tab.key)}
                className={[
                  "rounded-md px-3 py-1.5 text-xs transition-colors",
                  briefTab === tab.key
                    ? "bg-[var(--desk-ink)] text-[var(--desk-text)]"
                    : "text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
                ].join(" ")}
              >
                {tab.label}
              </button>
            ))}
          </div>
        }
      >
        <SessionBrief
          title={briefTab === "preopen" ? "开盘前" : "竞价后"}
          content={activeBrief?.content}
          emptyHint={
            emptyDay
              ? "该日暂无数据。"
              : "暂无摘要。点击「运行早盘」生成开盘前与竞价结果。"
          }
        />
      </SessionPanel>

      <div className="grid gap-4 xl:grid-cols-5">
        <div className="xl:col-span-2">
          <SessionPanel title="强势板块" hint="按竞价均涨与成分热度打分。">
            <SessionTable>
              <thead>
                <tr>
                  <th className={thClass}>#</th>
                  <th className={thClass}>板块</th>
                  <th className={thClass}>竞价均涨</th>
                  <th className={thClass}>成分</th>
                  <th className={thClass}>得分</th>
                </tr>
              </thead>
              <tbody>
                {boards.map((board, index) => (
                  <tr key={board.board || board.code || board.name} className="border-t border-[var(--desk-line)]">
                    <td className={`${tdClass} font-mono text-[var(--desk-mist)]`}>{index + 1}</td>
                    <td className={`${tdClass} font-medium text-[var(--desk-text)]`}>
                      {board.board || board.name || board.code || "—"}
                    </td>
                    <td className={`${tdClass} font-mono ${chgToneClass(board.avg_pct)}`}>
                      {formatPct(board.avg_pct)}
                    </td>
                    <td className={`${tdClass} font-mono`}>{board.count ?? "—"}</td>
                    <td className={`${tdClass} font-mono`}>{formatScore(board.score)}</td>
                  </tr>
                ))}
                {!boards.length && (
                  <EmptyRow
                    colSpan={5}
                    message={
                      emptyDay
                        ? "该日暂无数据。"
                        : hasRun
                          ? "本次未选出符合条件的板块。"
                          : "暂无板块。需先有竞价快照并完成选拔。"
                    }
                  />
                )}
              </tbody>
            </SessionTable>
          </SessionPanel>
        </div>

        <div className="xl:col-span-3">
          <SessionPanel
            title="强势个股"
            hint="按竞价上涨标的聚合；非自选名单。"
            action={
              <PrimaryAction
                isDisabled={busy || !stocks.length}
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
                  <th className={thClass}>竞价涨幅</th>
                  <th className={thClass}>竞价额</th>
                  <th className={thClass}>板块</th>
                  <th className={thClass}>策略</th>
                  <th className={thClass}>得分</th>
                </tr>
              </thead>
              <tbody>
                {stockPage.slice.map((stock, index) => {
                  const symbol = stock.symbol || stock.code || "";
                  const rowNo = (stockPage.page - 1) * stockPage.pageSize + index + 1;
                  return (
                    <tr
                      key={symbol}
                      className={trClickClass}
                      onClick={() => symbol && setDrawerSymbol(symbol)}
                    >
                      <td className={`${tdClass} font-mono text-[var(--desk-mist)]`}>{rowNo}</td>
                      <td className={`${tdClass} font-mono text-[var(--desk-text)]`}>
                        {symbol || "—"}
                      </td>
                      <td className={tdClass}>{stock.name || "—"}</td>
                      <td className={`${tdClass} font-mono`}>{formatPrice(stock.price)}</td>
                      <td className={`${tdClass} font-mono ${chgToneClass(stock.auction_pct)}`}>
                        {formatPct(stock.auction_pct)}
                      </td>
                      <td className={`${tdClass} font-mono`}>
                        {formatCompact(stock.auction_amount)}
                      </td>
                      <td className={tdClass}>{stock.board || "—"}</td>
                      <td className={`${tdClass} text-xs`}>
                        {formatStrategyLabel(stock.strategy_id || "auction_strong")}
                      </td>
                      <td className={`${tdClass} font-mono`}>{formatScore(stock.score)}</td>
                    </tr>
                  );
                })}
                {!stocks.length && (
                  <EmptyRow
                    colSpan={9}
                    message={
                      emptyDay
                        ? "该日暂无数据。"
                        : hasRun
                          ? "本次未选出竞价上涨个股。"
                          : "暂无个股。请点击「运行早盘」拉取竞价快照并选拔。"
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
        </div>
      </div>

      <ResearchPicksPanel
        picks={researchPicks}
        busy={busy}
        onRun={() => void runResearchRefine()}
        emptyHint={
          emptyDay
            ? "该日暂无数据。"
            : stocks.length
              ? "暂无投研精选。点击「投研精选」对当前强势个股打分。"
              : "暂无投研精选。请先完成早盘选拔后再运行。"
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
