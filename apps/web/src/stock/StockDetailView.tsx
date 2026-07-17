import { Alert, Button, Card, CardContent, CardHeader, CardTitle, Chip, Spinner } from "@heroui/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { summarizeIntradayBars, buildSmaSeries, DAILY_MA_LINES, toChartBars } from "./format";
import { calcPctChg, detectLimitTag } from "./limitStatus";
import { StockChart } from "./StockChart";
import type { ChartPeriod, OhlcvBar, PositionContext } from "./types";

type Props = {
  symbol: string;
  position?: PositionContext | null;
  compact?: boolean;
  onExpand?: () => void;
  onClose?: () => void;
};

type Quote = {
  name?: string;
  last?: number;
  pre_close?: number;
  pct_chg?: number;
  amount?: number;
  updated_at?: string;
};

type Meta = {
  symbol: string;
  name: string;
  is_delisted: boolean;
  status: string;
  updated_at?: string | null;
};

type Board = {
  board_code: string;
  board_name: string;
  board_type: string;
};

type CapitalFlow = {
  available: boolean;
  source?: string;
  latest?: Record<string, number | null>;
  series?: unknown[];
  error?: string;
};

type Technicals = {
  available: boolean;
  source?: string;
  latest?: {
    ma5?: number | null;
    ma10?: number | null;
    ma20?: number | null;
    macd?: number | null;
    macd_signal?: number | null;
    macd_hist?: number | null;
    rsi14?: number | null;
  };
  series?: unknown[];
  error?: string;
};

type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

const PERIODS: Array<{ value: ChartPeriod; label: string }> = [
  { value: "intraday", label: "分时" },
  { value: "day", label: "日 K" },
  { value: "week", label: "周 K" },
  { value: "month", label: "月 K" },
];

/**
 * 展示单只股票的报价、仓位、K 线和基础分析数据。
 * @param props 标的、可选仓位及嵌入式视图控制项
 */
export function StockDetailView({
  symbol,
  position = null,
  compact = false,
  onExpand,
  onClose,
}: Props) {
  const normalizedSymbol = symbol.trim().toUpperCase();
  const [period, setPeriod] = useState<ChartPeriod>("intraday");
  const [positionCollapsed, setPositionCollapsed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [notFound, setNotFound] = useState(false);
  const [quote, setQuote] = useState<LoadState<Quote>>(loadingState());
  const [meta, setMeta] = useState<LoadState<Meta>>(loadingState());
  const [boards, setBoards] = useState<LoadState<Board[]>>(loadingState());
  const [capitalFlow, setCapitalFlow] = useState<LoadState<CapitalFlow>>(loadingState());
  const [technicals, setTechnicals] = useState<LoadState<Technicals>>(loadingState());
  const [bars, setBars] = useState<LoadState<OhlcvBar[]>>(loadingState());

  const intradaySummary = useMemo(() => {
    if (period !== "intraday" || !bars.data?.length) return null;
    return summarizeIntradayBars(bars.data);
  }, [bars.data, period]);

  const dailyMaPrices = useMemo(() => {
    if (period !== "day" || !bars.data?.length) return [];
    const chartBars = toChartBars(bars.data, "day");
    return DAILY_MA_LINES.map((ma) => {
      const points = buildSmaSeries(chartBars, ma.window);
      const latest = points.length > 0 ? points[points.length - 1].value : null;
      return { ...ma, value: latest };
    });
  }, [bars.data, period]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setNotFound(false);
      setQuote(loadingState());
      setMeta(loadingState());
      setBoards(loadingState());
      setCapitalFlow(loadingState());
      setTechnicals(loadingState());

      const [quoteResult, metaResult, boardsResult, capitalFlowResult, technicalsResult] =
        await Promise.allSettled([
          api<Record<string, Quote>>(
            `/api/market/intraday/quote?symbols=${encodeURIComponent(normalizedSymbol)}`
          ),
          api<Meta>(`/api/market/stock/${encodeURIComponent(normalizedSymbol)}/meta`),
          api<{ boards: Board[] }>(`/api/market/stock/${encodeURIComponent(normalizedSymbol)}/boards`),
          api<CapitalFlow>(`/api/market/stock/${encodeURIComponent(normalizedSymbol)}/capital-flow`),
          api<Technicals>(`/api/market/stock/${encodeURIComponent(normalizedSymbol)}/technicals`),
        ]);

      if (cancelled) return;

      setQuote(resultState(quoteResult, (data) => data[normalizedSymbol] ?? Object.values(data)[0] ?? {}));
      if (metaResult.status === "rejected" && isNotFoundError(metaResult.reason)) {
        setNotFound(true);
      }
      setMeta(resultState(metaResult));
      setBoards(resultState(boardsResult, (data) => data.boards));
      setCapitalFlow(resultState(capitalFlowResult));
      setTechnicals(resultState(technicalsResult));
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [normalizedSymbol, reloadKey]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setBars(loadingState());

      const [barsResult] = await Promise.allSettled([loadBars(normalizedSymbol, period)]);

      if (cancelled) return;

      setBars(resultState(barsResult));
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [normalizedSymbol, period, reloadKey]);

  const displayName = meta.data?.name ?? quote.data?.name ?? normalizedSymbol;
  const lastPrice = quote.data?.last;
  const preClose = quote.data?.pre_close;
  const quoteChange =
    quote.data?.pct_chg != null && Number.isFinite(Number(quote.data.pct_chg))
      ? Number(quote.data.pct_chg)
      : calcPctChg(lastPrice, preClose) ?? 0;
  const limitTag = detectLimitTag(normalizedSymbol, lastPrice, preClose, displayName);

  if (notFound) {
    return (
      <Alert color="warning" title="未找到该标的">
        未找到代码 {normalizedSymbol}，请检查股票代码是否正确。
      </Alert>
    );
  }

  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-[var(--desk-text)]">{displayName}</h1>
              <span className="font-mono text-sm text-[var(--desk-mist)]">{normalizedSymbol}</span>
              {meta.data?.status && <Chip size="sm" variant="soft">{meta.data.status}</Chip>}
              {limitTag === "up" && (
                <Chip size="sm" color="danger" variant="soft">
                  涨停
                </Chip>
              )}
              {limitTag === "down" && (
                <Chip size="sm" color="success" variant="soft">
                  跌停
                </Chip>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {onExpand && (
                <Button size="sm" variant="secondary" onPress={onExpand}>
                  展开
                </Button>
              )}
              <Button size="sm" variant="secondary" onPress={() => setReloadKey((value) => value + 1)}>
                刷新
              </Button>
              {onClose && (
                <Button size="sm" variant="ghost" onPress={onClose}>
                  关闭
                </Button>
              )}
            </div>
          </div>
          {quote.loading ? (
            <div className="mt-3 flex items-center gap-2 text-sm text-[var(--desk-mist)]">
              <Spinner size="sm" /> 正在加载报价
            </div>
          ) : quote.error ? (
            <p className="mt-3 text-sm text-[var(--danger)]">报价加载失败：{quote.error}</p>
          ) : (
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <span className="font-mono text-3xl font-semibold text-[var(--desk-text)]">
                {formatNumber(lastPrice)}
              </span>
              <span className={`font-mono text-sm ${valueClass(quoteChange)}`}>
                {formatSigned(quoteChange)}%
              </span>
              {preClose != null && (
                <span className="text-xs text-[var(--desk-mist)]">昨收 {formatNumber(preClose)}</span>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {position && (
        <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
          <CardHeader className="flex items-center justify-between p-4 pb-2">
            <CardTitle className="text-sm text-[var(--desk-text)]">持仓信息</CardTitle>
            <Button size="sm" variant="ghost" onPress={() => setPositionCollapsed((value) => !value)}>
              {positionCollapsed ? "展开" : "收起"}
            </Button>
          </CardHeader>
          {!positionCollapsed && (
            <CardContent className="grid grid-cols-2 gap-3 p-4 pt-1 sm:grid-cols-4">
              <Metric label="持仓数量" value={formatNumber(position.qty, 0)} />
              <Metric label="持仓成本" value={formatNumber(position.cost)} />
              <Metric label="浮动盈亏" value={formatSigned(position.pnl)} tone={position.pnl} />
              <Metric
                label="盈亏比例"
                value={position.pnlPct == null ? "—" : `${formatSigned(position.pnlPct)}%`}
                tone={position.pnlPct}
              />
            </CardContent>
          )}
        </Card>
      )}

      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardContent className="space-y-3 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-1">
              {PERIODS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={[
                    "rounded-md px-3 py-1.5 text-sm transition-colors",
                    period === item.value
                      ? "bg-[var(--desk-accent)] font-medium text-[var(--desk-panel)]"
                      : "text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
                  ].join(" ")}
                  onClick={() => setPeriod(item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1 text-xs">
              {intradaySummary && (
                <>
                  <PriceChip label="均价" value={formatNumber(intradaySummary.avg)} />
                  <PriceChip label="开" value={formatNumber(intradaySummary.open)} />
                  <PriceChip label="收" value={formatNumber(intradaySummary.close)} />
                  <PriceChip label="高" value={formatNumber(intradaySummary.high)} />
                  <PriceChip label="低" value={formatNumber(intradaySummary.low)} />
                </>
              )}
              {dailyMaPrices.map((ma) => (
                <span key={ma.label} className="inline-flex items-center gap-1 font-mono whitespace-nowrap">
                  <span className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: ma.color }} />
                  <span style={{ color: ma.color }}>
                    {ma.label} {formatNumber(ma.value)}
                  </span>
                </span>
              ))}
            </div>
          </div>
          {bars.loading ? (
            <LoadingBlock label="正在加载行情数据" compact={compact} />
          ) : bars.error ? (
            <ErrorBlock message={`行情数据加载失败：${bars.error}`} />
          ) : (
            <StockChart period={period} bars={bars.data ?? []} compact={compact} />
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <SectionCard title="基本信息" state={meta}>
          {meta.data && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <InfoRow label="股票代码" value={meta.data.symbol} mono />
              <InfoRow label="上市状态" value={meta.data.status} />
              <InfoRow label="是否退市" value={meta.data.is_delisted ? "是" : "否"} />
              <InfoRow label="更新时间" value={formatDateTime(meta.data.updated_at)} />
              <InfoRow label="成交额" value={formatCompactNumber(quote.data?.amount)} />
            </dl>
          )}
        </SectionCard>

        <SectionCard title="行业概念" state={boards}>
          {(boards.data?.length ?? 0) > 0 ? (
            <div className="flex flex-wrap gap-2">
              {boards.data?.map((board) => (
                <Chip key={`${board.board_type}-${board.board_code}`} variant="soft">
                  {board.board_name}
                </Chip>
              ))}
            </div>
          ) : (
            <EmptyCopy text="暂无行业或概念数据" />
          )}
        </SectionCard>

        <SectionCard title="资金面" state={capitalFlow}>
          {capitalFlow.data?.available ? (
            <div className="space-y-3">
              <p className="text-xs text-[var(--desk-mist)]">数据来源：{capitalFlow.data.source ?? "—"}</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Metric label="主力净流入" value={formatCompactNumber(capitalFlow.data.latest?.main_net)} tone={capitalFlow.data.latest?.main_net} />
                <Metric label="超大单" value={formatCompactNumber(capitalFlow.data.latest?.super_net)} tone={capitalFlow.data.latest?.super_net} />
                <Metric label="大单" value={formatCompactNumber(capitalFlow.data.latest?.large_net)} tone={capitalFlow.data.latest?.large_net} />
              </div>
            </div>
          ) : (
            <EmptyCopy text={capitalFlow.data?.error ? `资金数据暂不可用：${capitalFlow.data.error}` : "暂无资金流数据"} />
          )}
        </SectionCard>

        <SectionCard title="技术面" state={technicals}>
          {technicals.data?.available ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Metric label="MA5" value={formatNumber(technicals.data.latest?.ma5)} />
              <Metric label="MA10" value={formatNumber(technicals.data.latest?.ma10)} />
              <Metric label="MA20" value={formatNumber(technicals.data.latest?.ma20)} />
              <Metric label="MACD" value={formatNumber(technicals.data.latest?.macd)} tone={technicals.data.latest?.macd} />
              <Metric label="RSI(14)" value={formatNumber(technicals.data.latest?.rsi14)} />
            </div>
          ) : (
            <EmptyCopy text={technicals.data?.error ? `技术指标暂不可用：${technicals.data.error}` : "暂无技术指标数据"} />
          )}
        </SectionCard>
      </div>
    </div>
  );
}

/**
 * 请求与当前周期相符的行情数据。
 * @param symbol 股票代码
 * @param period 图表周期
 */
async function loadBars(symbol: string, period: ChartPeriod): Promise<OhlcvBar[]> {
  if (period === "intraday") {
    const date = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
    const params = new URLSearchParams({
      symbol,
      from: `${date}T09:30:00+08:00`,
      to: `${date}T15:00:00+08:00`,
    });
    return api<OhlcvBar[]>(`/api/market/bars/minute?${params}`);
  }

  const today = new Date();
  const from = new Date(today);
  from.setFullYear(today.getFullYear() - 1);
  const params = new URLSearchParams({
    symbol,
    from: toDateString(from),
    to: toDateString(today),
    ...(period === "day" ? {} : { period }),
  });
  return api<OhlcvBar[]>(`/api/market/bars/daily?${params}`);
}

/**
 * 创建处于加载中的分区状态。
 */
function loadingState<T>(): LoadState<T> {
  return { data: null, loading: true, error: null };
}

/**
 * 将 Promise.allSettled 的结果转换为页面分区状态。
 * @param result 请求结果
 * @param mapData 可选的数据映射
 */
function resultState<T, U = T>(
  result: PromiseSettledResult<T>,
  mapData?: (data: T) => U
): LoadState<U> {
  if (result.status === "fulfilled") {
    return { data: mapData ? mapData(result.value) : (result.value as unknown as U), loading: false, error: null };
  }
  return { data: null, loading: false, error: errorMessage(result.reason) };
}

/**
 * 判断接口异常是否对应元数据 404。
 * @param error 请求异常
 */
function isNotFoundError(error: unknown): boolean {
  return errorMessage(error).includes("symbol not found");
}

/**
 * 取得可展示的异常文本。
 * @param error 未知异常
 */
function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * 转换为 API 所需的本地日期字符串。
 * @param value 日期对象
 */
function toDateString(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

/**
 * 展示独立分区的加载、错误和内容状态。
 * @param props 卡片标题、请求状态及内容
 */
function SectionCard<T>({
  title,
  state,
  children,
}: {
  title: string;
  state: LoadState<T>;
  children: ReactNode;
}) {
  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="p-5 pb-2">
        <CardTitle className="text-base text-[var(--desk-text)]">{title}</CardTitle>
      </CardHeader>
      <CardContent className="min-h-24 p-5 pt-2">
        {state.loading ? <LoadingBlock label="正在加载" /> : state.error ? <ErrorBlock message={state.error} /> : children}
      </CardContent>
    </Card>
  );
}

/**
 * 展示小型指标块。
 * @param props 指标文案、数值及涨跌颜色
 */
function Metric({ label, value, tone }: { label: string; value: string; tone?: number | null }) {
  return (
    <div className="rounded-md bg-[var(--desk-ink)] p-3">
      <p className="text-xs text-[var(--desk-mist)]">{label}</p>
      <p className={`mt-1 font-mono text-sm ${tone == null ? "text-[var(--desk-text)]" : valueClass(tone)}`}>{value}</p>
    </div>
  );
}

/**
 * 顶栏紧凑价格项。
 * @param props 标签与数值
 */
function PriceChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="font-mono text-[var(--desk-text)] whitespace-nowrap">
      <span className="text-[var(--desk-mist)]">{label} </span>
      {value}
    </span>
  );
}

/**
 * 展示基础信息键值行。
 * @param props 标签、文本及等宽字选项
 */
function InfoRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-[var(--desk-mist)]">{label}</dt>
      <dd className={`mt-1 text-[var(--desk-text)] ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

/**
 * 展示通用加载状态。
 * @param props 展示文字与紧凑模式
 */
function LoadingBlock({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div className={`flex items-center justify-center gap-2 text-sm text-[var(--desk-mist)] ${compact ? "h-48" : "h-20"}`}>
      <Spinner size="sm" /> {label}
    </div>
  );
}

/**
 * 展示分区请求错误。
 * @param props 错误文本
 */
function ErrorBlock({ message }: { message: string }) {
  return <p className="text-sm text-[var(--danger)]">{message}</p>;
}

/**
 * 展示无可用数据的提示文本。
 * @param props 提示文本
 */
function EmptyCopy({ text }: { text: string }) {
  return <p className="text-sm text-[var(--desk-mist)]">{text}</p>;
}

/**
 * 格式化数值。
 * @param value 数值
 * @param digits 小数位
 */
function formatNumber(value: number | undefined | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * 格式化带正负号数值。
 * @param value 数值
 * @param digits 小数位
 */
function formatSigned(value: number | undefined | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : value < 0 ? "-" : ""}${formatNumber(Math.abs(value), digits)}`;
}

/**
 * 使用中文缩写格式化较大的金额。
 * @param value 数值
 */
function formatCompactNumber(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`;
  if (Math.abs(value) >= 10_000) return `${(value / 10_000).toFixed(2)}万`;
  return formatNumber(value);
}

/**
 * 按涨跌返回 Desk 主题文本颜色。
 * @param value 数值
 */
function valueClass(value: number): string {
  if (value > 0) return "text-[var(--danger)]";
  if (value < 0) return "text-[var(--success)]";
  return "text-[var(--desk-mist)]";
}

/**
 * 格式化接口返回的更新时间。
 * @param value ISO 时间
 */
function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}
