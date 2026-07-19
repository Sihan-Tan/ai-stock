import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

type StrategyOpt = {
  id: string;
  name: string;
};

type AppSettings = {
  trade_mode: "paper" | "live" | string;
  auto_execute_live?: boolean;
  i_understand_auto_live?: boolean;
  qmt_force_mock?: boolean;
  paper_default_strategy_id?: string;
  paper_runner_enabled?: boolean;
  paper_runner_strategy_id?: string;
  paper_runner_interval_minutes?: number;
  ml_engine: "lightgbm" | "xgboost" | string;
  llm_provider: string;
  llm_api_key: string;
  llm_api_key_set?: boolean;
  llm_base_url: string;
  llm_model: string;
  feishu_webhook_url: string;
  feishu_sign_secret: string;
  feishu_sign_secret_set?: boolean;
  qmt_userdata_path: string;
  qmt_account_id: string;
  paper_initial_cash: number;
  backtest_buy_commission: number;
  backtest_sell_commission: number;
  backtest_stamp_duty: number;
  backtest_min_commission: number;
  backtest_slippage: number;
  risk_max_order_position_pct: number;
  risk_max_order_notional: number;
  risk_max_daily_notional: number;
  risk_max_positions?: number;
  risk_armed?: boolean;
  risk_kill_switch?: boolean;
  risk_whitelist?: string;
};

const EMPTY: AppSettings = {
  trade_mode: "paper",
  auto_execute_live: false,
  i_understand_auto_live: false,
  qmt_force_mock: true,
  paper_default_strategy_id: "ma_cross",
  paper_runner_enabled: false,
  paper_runner_strategy_id: "ma_cross",
  paper_runner_interval_minutes: 30,
  ml_engine: "lightgbm",
  llm_provider: "deepseek",
  llm_api_key: "",
  llm_base_url: "",
  llm_model: "",
  feishu_webhook_url: "",
  feishu_sign_secret: "",
  qmt_userdata_path: "",
  qmt_account_id: "",
  paper_initial_cash: 1_000_000,
  backtest_buy_commission: 0.00025,
  backtest_sell_commission: 0.00025,
  backtest_stamp_duty: 0.001,
  backtest_min_commission: 5,
  backtest_slippage: 0.001,
  risk_max_order_position_pct: 10,
  risk_max_order_notional: 50_000,
  risk_max_daily_notional: 200_000,
  risk_max_positions: 4,
  risk_armed: false,
  risk_kill_switch: false,
  risk_whitelist: "",
};

/** 设置页模块 Tab */
const SETTINGS_TABS = [
  { id: "trading", label: "交易模式" },
  { id: "risk", label: "风控闸门" },
  { id: "fees", label: "手续费" },
  { id: "ml", label: "机器学习" },
  { id: "llm", label: "LLM" },
  { id: "feishu", label: "飞书告警" },
  { id: "qmt", label: "miniQMT" },
] as const;

type SettingsTabId = (typeof SETTINGS_TABS)[number]["id"];

/**
 * 策略下拉选项：保证当前值始终可选；列表为空时回退 ma_cross。
 * @param strategies 策略列表
 * @param currentId 当前选中 ID
 */
function strategySelectOptions(strategies: StrategyOpt[], currentId: string): StrategyOpt[] {
  const fallback: StrategyOpt[] = strategies.length
    ? strategies
    : [{ id: "ma_cross", name: "双均线" }];
  const id = (currentId || "ma_cross").trim();
  if (fallback.some((s) => s.id === id)) {
    return fallback;
  }
  return [{ id, name: id }, ...fallback];
}

/**
 * 应用设置：模式 / ML / LLM / 手续费 / 风控闸门 / 飞书等，写入 .env。
 * @param props 页面日志
 */
export default function Settings({ setLog }: PageLogProps) {
  const [form, setForm] = useState<AppSettings>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [strategies, setStrategies] = useState<StrategyOpt[]>([]);
  const [tab, setTab] = useState<SettingsTabId>("trading");

  /**
   * 加载当前配置与策略列表。
   */
  const load = async () => {
    setBusy(true);
    try {
      const [data, list] = await Promise.all([
        api<AppSettings>("/api/settings"),
        api<StrategyOpt[]>("/api/strategies").catch(() => [] as StrategyOpt[]),
      ]);
      setForm({ ...EMPTY, ...data });
      setStrategies(list.map((s) => ({ id: s.id, name: s.name || s.id })));
      setDirty(false);
      setLog("已加载设置");
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  /**
   * 更新表单字段。
   */
  const patch = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  /**
   * 保存到后端（持久化 .env）。
   */
  const save = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        trade_mode: form.trade_mode,
        auto_execute_live: Boolean(form.auto_execute_live),
        i_understand_auto_live: Boolean(form.i_understand_auto_live),
        qmt_force_mock: Boolean(form.qmt_force_mock),
        paper_default_strategy_id: form.paper_default_strategy_id || "ma_cross",
        paper_runner_enabled: Boolean(form.paper_runner_enabled),
        paper_runner_strategy_id: form.paper_runner_strategy_id || "ma_cross",
        paper_runner_interval_minutes: Number(form.paper_runner_interval_minutes) || 30,
        ml_engine: form.ml_engine,
        llm_provider: form.llm_provider,
        llm_base_url: form.llm_base_url,
        llm_model: form.llm_model,
        feishu_webhook_url: form.feishu_webhook_url,
        qmt_userdata_path: form.qmt_userdata_path,
        qmt_account_id: form.qmt_account_id,
        paper_initial_cash: Number(form.paper_initial_cash),
        backtest_buy_commission: Number(form.backtest_buy_commission),
        backtest_sell_commission: Number(form.backtest_sell_commission),
        backtest_stamp_duty: Number(form.backtest_stamp_duty),
        backtest_min_commission: Number(form.backtest_min_commission),
        backtest_slippage: Number(form.backtest_slippage),
        risk_max_order_position_pct: Number(form.risk_max_order_position_pct),
        risk_max_order_notional: Number(form.risk_max_order_notional),
        risk_max_daily_notional: Number(form.risk_max_daily_notional),
        risk_max_positions: Math.max(0, Math.floor(Number(form.risk_max_positions) || 0)),
        risk_armed: Boolean(form.risk_armed),
        risk_kill_switch: Boolean(form.risk_kill_switch),
        risk_whitelist: form.risk_whitelist || "",
      };
      if (form.llm_api_key && !form.llm_api_key.includes("*")) {
        body.llm_api_key = form.llm_api_key;
      }
      if (form.feishu_sign_secret && !form.feishu_sign_secret.includes("*")) {
        body.feishu_sign_secret = form.feishu_sign_secret;
      }
      const saved = await api<AppSettings>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setForm({ ...EMPTY, ...saved });
      setDirty(false);
      setLog("设置已保存到 .env");
    } catch (error) {
      setLog(String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
        <CardHeader className="flex w-full flex-row flex-nowrap items-center justify-between gap-3 p-5 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <CardTitle className="text-base text-[var(--desk-text)]">设置</CardTitle>
            {dirty ? (
              <Chip size="sm" variant="soft" color="warning">
                未保存
              </Chip>
            ) : (
              <Chip size="sm" variant="soft" color="success">
                已同步
              </Chip>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => void load()}>
              重新加载
            </Button>
            <Button size="sm" variant="primary" isDisabled={busy || !dirty} onPress={() => void save()}>
              {busy ? "保存中…" : "保存设置"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-2">
          <p className="text-xs text-[var(--desk-mist)]">
            保存后写入项目根目录 <code>.env</code>，并立即刷新进程内配置；密钥留空表示保持原值。切换
            Tab 不会丢失未保存修改。
          </p>

          <div
            role="tablist"
            aria-label="设置模块"
            className="flex gap-1 overflow-x-auto border-b border-[var(--desk-line)] pb-px"
          >
            {SETTINGS_TABS.map((item) => {
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  id={`settings-tab-${item.id}`}
                  aria-controls={`settings-panel-${item.id}`}
                  className={[
                    "shrink-0 rounded-t-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "border-b-2 border-[var(--desk-accent)] font-medium text-[var(--desk-text)]"
                      : "border-b-2 border-transparent text-[var(--desk-mist)] hover:text-[var(--desk-text)]",
                  ].join(" ")}
                  onClick={() => setTab(item.id)}
                >
                  {item.label}
                </button>
              );
            })}
          </div>

          <div
            role="tabpanel"
            id={`settings-panel-${tab}`}
            aria-labelledby={`settings-tab-${tab}`}
            className="min-h-[280px]"
          >
            {tab === "trading" && (
              <TabPanel title="交易模式与 Runner">
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="模式">
                    <select
                      className={inputClass}
                      value={form.trade_mode}
                      onChange={(e) => patch("trade_mode", e.target.value)}
                    >
                      <option value="paper">模拟 (paper)</option>
                      <option value="live">实盘 (live)</option>
                    </select>
                  </Field>
                  <Field label="模拟初始资金">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.paper_initial_cash)}
                      onChange={(e) => patch("paper_initial_cash", Number(e.target.value) || 0)}
                    />
                  </Field>
                </div>
                <div className="mt-4 space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4">
                  <div className="text-sm font-medium text-[var(--desk-text)]">实盘执行（双开关）</div>
                  <p className="text-xs text-[var(--desk-mist)]">
                    默认关闭自动成交：live 订单进入审批队列。两开关同时开启才自动成交。
                  </p>
                  <label className="flex items-start gap-2 text-sm text-[var(--desk-text)]">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(form.auto_execute_live)}
                      onChange={(e) => patch("auto_execute_live", e.target.checked)}
                    />
                    <span>
                      自动成交（AUTO_EXECUTE_LIVE）
                      <span className="mt-0.5 block text-xs text-[var(--desk-mist)]">
                        关闭时实盘单为「待审批」
                      </span>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 text-sm text-[var(--desk-text)]">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(form.i_understand_auto_live)}
                      onChange={(e) => patch("i_understand_auto_live", e.target.checked)}
                    />
                    <span>
                      我已理解自动实盘风险（I_UNDERSTAND_AUTO_LIVE）
                      <span className="mt-0.5 block text-xs text-[var(--desk-mist)]">
                        需与上一开关同时开启才会自动成交
                      </span>
                    </span>
                  </label>
                  <p className="text-xs text-[var(--desk-mist)]">
                    当前实盘子模式：{" "}
                    <span className="font-mono text-[var(--desk-text)]">
                      {!form.auto_execute_live
                        ? "approval（审批）"
                        : form.i_understand_auto_live
                          ? "auto（自动）"
                          : "blocked（缺确认）"}
                    </span>
                  </p>
                  <label className="flex items-start gap-2 text-sm text-[var(--desk-text)]">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(form.qmt_force_mock)}
                      onChange={(e) => patch("qmt_force_mock", e.target.checked)}
                    />
                    <span>
                      强制 Mock 不发真单（QMT_FORCE_MOCK）
                      <span className="mt-0.5 block text-xs text-[var(--desk-mist)]">
                        仅拦截真下单；持仓/资金仍可从 QMT 柜台查询。取消勾选且账号/路径齐全时发真单
                      </span>
                    </span>
                  </label>
                  <Field label="纸交易默认策略（手动买入闸门）">
                    <select
                      className={inputClass}
                      value={form.paper_default_strategy_id || "ma_cross"}
                      onChange={(e) => patch("paper_default_strategy_id", e.target.value)}
                    >
                      {strategySelectOptions(
                        strategies,
                        form.paper_default_strategy_id || "ma_cross"
                      ).map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.id})
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <div className="mt-4 space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4">
                  <div className="text-sm font-medium text-[var(--desk-text)]">Paper Runner 定时</div>
                  <p className="text-xs text-[var(--desk-mist)]">
                    交易时段按间隔扫描自选，并在 15:35 补跑。改开关/间隔后需重启 API。
                  </p>
                  <label className="flex items-center gap-2 text-sm text-[var(--desk-text)]">
                    <input
                      type="checkbox"
                      checked={Boolean(form.paper_runner_enabled)}
                      onChange={(e) => patch("paper_runner_enabled", e.target.checked)}
                    />
                    启用定时 Runner
                  </label>
                  <div className="grid gap-3 md:grid-cols-2">
                    <Field label="Runner 策略">
                      <select
                        className={inputClass}
                        value={form.paper_runner_strategy_id || "ma_cross"}
                        onChange={(e) => patch("paper_runner_strategy_id", e.target.value)}
                      >
                        {strategySelectOptions(
                          strategies,
                          form.paper_runner_strategy_id || "ma_cross"
                        ).map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name} ({s.id})
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="间隔（分钟）">
                      <input
                        className={inputClass}
                        inputMode="numeric"
                        value={String(form.paper_runner_interval_minutes ?? 30)}
                        onChange={(e) =>
                          patch("paper_runner_interval_minutes", Number(e.target.value) || 30)
                        }
                      />
                    </Field>
                  </div>
                </div>
              </TabPanel>
            )}

            {tab === "risk" && (
              <TabPanel title="风控与实盘闸门">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <Field label="单笔最大仓位（占总权益 %）">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.risk_max_order_position_pct)}
                      onChange={(e) =>
                        patch("risk_max_order_position_pct", Number(e.target.value))
                      }
                    />
                  </Field>
                  <Field label="单笔最大金额（元）">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.risk_max_order_notional)}
                      onChange={(e) => patch("risk_max_order_notional", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="单日最大金额（元）">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.risk_max_daily_notional)}
                      onChange={(e) => patch("risk_max_daily_notional", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="最多持仓股票数（只）">
                    <input
                      className={inputClass}
                      inputMode="numeric"
                      value={String(form.risk_max_positions ?? 4)}
                      onChange={(e) =>
                        patch("risk_max_positions", Math.max(0, Number(e.target.value) || 0))
                      }
                    />
                  </Field>
                </div>
                <p className="mt-2 text-xs text-[var(--desk-mist)]">
                  单笔上限取「权益×仓位%」与「单笔最大金额」较小者；买入新标的时受「最多持仓股票数」限制（0=不限制）；加仓已有标的不占新名额。限额对模拟与实盘均生效。
                </p>
                <div className="mt-4 space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4">
                  <div className="text-sm font-medium text-[var(--desk-text)]">
                    实盘 ARM / Kill / 白名单
                  </div>
                  <label className="flex items-start gap-2 text-sm text-[var(--desk-text)]">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(form.risk_armed)}
                      onChange={(e) => patch("risk_armed", e.target.checked)}
                    />
                    <span>
                      ARM（允许实盘下单）
                      <span className="mt-0.5 block text-xs text-[var(--desk-mist)]">
                        未勾选时拒绝一切 live 订单
                      </span>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 text-sm text-[var(--desk-text)]">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(form.risk_kill_switch)}
                      onChange={(e) => patch("risk_kill_switch", e.target.checked)}
                    />
                    <span>
                      Kill Switch（熔断）
                      <span className="mt-0.5 block text-xs text-[var(--desk-mist)]">
                        勾选后拒绝 live；监控页应急按钮也会写入此项
                      </span>
                    </span>
                  </label>
                  <Field label="白名单（逗号分隔，空=不限制）">
                    <input
                      className={inputClass}
                      placeholder="600519.SH,000001.SZ"
                      value={form.risk_whitelist || ""}
                      onChange={(e) => patch("risk_whitelist", e.target.value)}
                    />
                  </Field>
                </div>
              </TabPanel>
            )}

            {tab === "fees" && (
              <TabPanel title="交易手续费（回测）">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  <Field label="买入佣金率">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.backtest_buy_commission)}
                      onChange={(e) => patch("backtest_buy_commission", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="卖出佣金率">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.backtest_sell_commission)}
                      onChange={(e) => patch("backtest_sell_commission", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="印花税（仅卖出）">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.backtest_stamp_duty)}
                      onChange={(e) => patch("backtest_stamp_duty", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="单笔最低佣金（元）">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.backtest_min_commission)}
                      onChange={(e) => patch("backtest_min_commission", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="滑点">
                    <input
                      className={inputClass}
                      inputMode="decimal"
                      value={String(form.backtest_slippage)}
                      onChange={(e) => patch("backtest_slippage", Number(e.target.value))}
                    />
                  </Field>
                </div>
              </TabPanel>
            )}

            {tab === "ml" && (
              <TabPanel title="机器学习">
                <Field label="ML 引擎">
                  <select
                    className={inputClass}
                    value={form.ml_engine}
                    onChange={(e) => patch("ml_engine", e.target.value)}
                  >
                    <option value="lightgbm">LightGBM</option>
                    <option value="xgboost">XGBoost</option>
                  </select>
                </Field>
              </TabPanel>
            )}

            {tab === "llm" && (
              <TabPanel title="LLM（投研对话）">
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="提供商">
                    <select
                      className={inputClass}
                      value={form.llm_provider}
                      onChange={(e) => patch("llm_provider", e.target.value)}
                    >
                      <option value="deepseek">DeepSeek</option>
                      <option value="openai">OpenAI</option>
                      <option value="chatgpt">ChatGPT</option>
                    </select>
                  </Field>
                  <Field label="模型">
                    <input
                      className={inputClass}
                      value={form.llm_model}
                      onChange={(e) => patch("llm_model", e.target.value)}
                    />
                  </Field>
                  <Field label="Base URL">
                    <input
                      className={inputClass}
                      value={form.llm_base_url}
                      onChange={(e) => patch("llm_base_url", e.target.value)}
                    />
                  </Field>
                  <Field
                    label={`API Key${form.llm_api_key_set ? "（已配置，留空不改）" : ""}`}
                  >
                    <input
                      className={inputClass}
                      type="password"
                      autoComplete="off"
                      placeholder={form.llm_api_key_set ? "••••••••" : "填入密钥"}
                      value={form.llm_api_key.includes("*") ? "" : form.llm_api_key}
                      onChange={(e) => patch("llm_api_key", e.target.value)}
                    />
                  </Field>
                </div>
              </TabPanel>
            )}

            {tab === "feishu" && (
              <TabPanel title="飞书告警">
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="Webhook 地址">
                    <input
                      className={inputClass}
                      value={form.feishu_webhook_url}
                      onChange={(e) => patch("feishu_webhook_url", e.target.value)}
                      placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                    />
                  </Field>
                  <Field
                    label={`签名密钥${form.feishu_sign_secret_set ? "（已配置，留空不改）" : ""}`}
                  >
                    <input
                      className={inputClass}
                      type="password"
                      autoComplete="off"
                      placeholder={form.feishu_sign_secret_set ? "••••••••" : "可选"}
                      value={
                        form.feishu_sign_secret.includes("*") ? "" : form.feishu_sign_secret
                      }
                      onChange={(e) => patch("feishu_sign_secret", e.target.value)}
                    />
                  </Field>
                </div>
              </TabPanel>
            )}

            {tab === "qmt" && (
              <TabPanel title="miniQMT">
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="userdata 路径">
                    <input
                      className={inputClass}
                      value={form.qmt_userdata_path}
                      onChange={(e) => patch("qmt_userdata_path", e.target.value)}
                    />
                  </Field>
                  <Field label="账户 ID">
                    <input
                      className={inputClass}
                      value={form.qmt_account_id}
                      onChange={(e) => patch("qmt_account_id", e.target.value)}
                    />
                  </Field>
                </div>
              </TabPanel>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * Tab 内容区标题与正文。
 * @param props 标题与子节点
 */
function TabPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-[var(--desk-text)]">{title}</h3>
      {children}
    </div>
  );
}

/**
 * 表单字段。
 * @param props 标签与控件
 */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs text-[var(--desk-mist)]">{label}</span>
      {children}
    </label>
  );
}
