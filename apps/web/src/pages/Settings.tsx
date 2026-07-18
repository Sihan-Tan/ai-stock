import { Button, Card, CardContent, CardHeader, CardTitle, Chip } from "@heroui/react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import type { PageLogProps } from "./types";

type AppSettings = {
  trade_mode: "paper" | "live" | string;
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
};

const EMPTY: AppSettings = {
  trade_mode: "paper",
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
};

/**
 * 应用设置：模式 / ML / LLM / 手续费 / 仓位限额 / 飞书等，写入 .env。
 * @param props 页面日志
 */
export default function Settings({ setLog }: PageLogProps) {
  const [form, setForm] = useState<AppSettings>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  /**
   * 加载当前配置。
   */
  const load = async () => {
    setBusy(true);
    try {
      const data = await api<AppSettings>("/api/settings");
      setForm({ ...EMPTY, ...data });
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
      };
      // 密钥：仅在用户重新输入（不含 *）时提交
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
        <CardContent className="p-5 pt-2">
          <p className="text-xs text-[var(--desk-mist)]">
            保存后写入项目根目录 <code>.env</code>，并立即刷新进程内配置；密钥留空表示保持原值。
          </p>
        </CardContent>
      </Card>

      <Section title="交易模式">
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
      </Section>

      <Section title="机器学习">
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
      </Section>

      <Section title="LLM（投研对话）">
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
      </Section>

      <Section title="交易手续费（回测）">
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
      </Section>

      <Section title="下单限额">
        <div className="grid gap-3 md:grid-cols-3">
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
        </div>
        <p className="mt-2 text-xs text-[var(--desk-mist)]">
          单笔上限取「总权益 × 仓位%」与「单笔最大金额」的较小者（默认仓位
          10%），另受单日最大金额限制。以上限额对
          <span className="text-[var(--desk-text)]">模拟与实盘下单均强制生效</span>
          ；实盘另需在「实盘风控」页 ARM / 白名单。
        </p>
      </Section>

      <Section title="飞书告警">
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
              value={form.feishu_sign_secret.includes("*") ? "" : form.feishu_sign_secret}
              onChange={(e) => patch("feishu_sign_secret", e.target.value)}
            />
          </Field>
        </div>
      </Section>

      <Section title="miniQMT">
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
      </Section>
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] px-3 py-2 text-sm text-[var(--desk-text)] outline-none focus:border-[var(--desk-mist)]";

/**
 * 设置分组卡片。
 */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="border border-[var(--desk-line)] bg-[var(--desk-panel)]">
      <CardHeader className="p-5 pb-3">
        <CardTitle className="text-base text-[var(--desk-text)]">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-5 pt-2">{children}</CardContent>
    </Card>
  );
}

/**
 * 表单字段。
 */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs text-[var(--desk-mist)]">{label}</span>
      {children}
    </label>
  );
}
