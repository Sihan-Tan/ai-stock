"""可写配置：读写 .env 并刷新 Settings 缓存。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from desk_common.settings import Settings, get_settings

# UI 可编辑字段 → 环境变量名
EDITABLE_ENV: dict[str, str] = {
    "trade_mode": "TRADE_MODE",
    "auto_execute_live": "AUTO_EXECUTE_LIVE",
    "i_understand_auto_live": "I_UNDERSTAND_AUTO_LIVE",
    "ml_engine": "ML_ENGINE",
    "llm_provider": "LLM_PROVIDER",
    "llm_api_key": "LLM_API_KEY",
    "llm_base_url": "LLM_BASE_URL",
    "llm_model": "LLM_MODEL",
    "feishu_webhook_url": "FEISHU_WEBHOOK_URL",
    "feishu_sign_secret": "FEISHU_SIGN_SECRET",
    "qmt_userdata_path": "QMT_USERDATA_PATH",
    "qmt_account_id": "QMT_ACCOUNT_ID",
    "qmt_force_mock": "QMT_FORCE_MOCK",
    "paper_initial_cash": "PAPER_INITIAL_CASH",
    "paper_default_strategy_id": "PAPER_DEFAULT_STRATEGY_ID",
    "paper_runner_enabled": "PAPER_RUNNER_ENABLED",
    "paper_runner_strategy_id": "PAPER_RUNNER_STRATEGY_ID",
    "paper_runner_interval_minutes": "PAPER_RUNNER_INTERVAL_MINUTES",
    "backtest_buy_commission": "BACKTEST_BUY_COMMISSION",
    "backtest_sell_commission": "BACKTEST_SELL_COMMISSION",
    "backtest_stamp_duty": "BACKTEST_STAMP_DUTY",
    "backtest_min_commission": "BACKTEST_MIN_COMMISSION",
    "backtest_slippage": "BACKTEST_SLIPPAGE",
    "risk_max_order_position_pct": "RISK_MAX_ORDER_POSITION_PCT",
    "risk_max_order_notional": "RISK_MAX_ORDER_NOTIONAL",
    "risk_max_daily_notional": "RISK_MAX_DAILY_NOTIONAL",
}

SECRET_FIELDS = frozenset({"llm_api_key", "feishu_sign_secret"})


def _env_path() -> Path:
    """定位仓库根目录 .env（相对进程 cwd 或本包向上查找）。"""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def _mask_secret(value: str) -> str:
    """密钥脱敏展示。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def public_settings() -> dict[str, Any]:
    """
    返回可供前端展示的配置（密钥脱敏）。

    @returns: 配置字典
    """
    s = get_settings()
    return {
        "trade_mode": s.trade_mode,
        "auto_execute_live": s.auto_execute_live,
        "i_understand_auto_live": s.i_understand_auto_live,
        "ml_engine": s.ml_engine,
        "llm_provider": s.llm_provider,
        "llm_api_key": _mask_secret(s.llm_api_key),
        "llm_api_key_set": bool(s.llm_api_key),
        "llm_base_url": s.llm_base_url,
        "llm_model": s.llm_model,
        "feishu_webhook_url": s.feishu_webhook_url,
        "feishu_sign_secret": _mask_secret(s.feishu_sign_secret),
        "feishu_sign_secret_set": bool(s.feishu_sign_secret),
        "qmt_userdata_path": s.qmt_userdata_path,
        "qmt_account_id": s.qmt_account_id,
        "qmt_force_mock": s.qmt_force_mock,
        "paper_initial_cash": s.paper_initial_cash,
        "paper_default_strategy_id": s.paper_default_strategy_id,
        "paper_runner_enabled": s.paper_runner_enabled,
        "paper_runner_strategy_id": s.paper_runner_strategy_id,
        "paper_runner_interval_minutes": s.paper_runner_interval_minutes,
        "backtest_buy_commission": s.backtest_buy_commission,
        "backtest_sell_commission": s.backtest_sell_commission,
        "backtest_stamp_duty": s.backtest_stamp_duty,
        "backtest_min_commission": s.backtest_min_commission,
        "backtest_slippage": s.backtest_slippage,
        "risk_max_order_position_pct": s.risk_max_order_position_pct,
        "risk_max_order_notional": s.risk_max_order_notional,
        "risk_max_daily_notional": s.risk_max_daily_notional,
    }


def _parse_env_file(text: str) -> list[tuple[str, str | None]]:
    """
    解析 .env 为有序行：(key, value)；注释/空行 value=None 且 key 为整行。

    @param text: 文件内容
    """
    rows: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            rows.append((line, None))
            continue
        if "=" not in stripped:
            rows.append((line, None))
            continue
        key, _, val = stripped.partition("=")
        rows.append((key.strip(), val.strip()))
    return rows


def _serialize_value(value: Any) -> str:
    """序列化为 .env 值。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def upsert_env(updates: dict[str, Any]) -> Path:
    """
    将字段补丁写入 .env，保留其余行。

    @param updates: Settings 字段名 → 值
    @returns: .env 路径
    """
    env_keys: dict[str, str] = {}
    for field, value in updates.items():
        mapped = EDITABLE_ENV.get(field)
        if not mapped:
            continue
        env_keys[mapped] = _serialize_value(value)

    path = _env_path()
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    rows = _parse_env_file(existing)
    seen: set[str] = set()
    out_lines: list[str] = []

    for key, val in rows:
        if val is None:
            out_lines.append(key)
            continue
        if key in env_keys:
            out_lines.append(f"{key}={env_keys[key]}")
            seen.add(key)
        else:
            out_lines.append(f"{key}={val}")

    for key, value in env_keys.items():
        if key not in seen:
            out_lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")

    for key, value in env_keys.items():
        os.environ[key] = value
    return path


def apply_settings_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """
    校验并持久化补丁，刷新 Settings 缓存。

    @param patch: 前端提交的字段（空密钥表示不改）
    @returns: 更新后的 public_settings
    """
    current = get_settings()
    cleaned: dict[str, Any] = {}

    for field, raw in patch.items():
        if field not in EDITABLE_ENV:
            continue
        if field in SECRET_FIELDS:
            text = "" if raw is None else str(raw).strip()
            if not text or "*" in text or text == _mask_secret(getattr(current, field)):
                continue
            cleaned[field] = text
            continue

        if raw is None:
            continue

        if field in (
            "paper_initial_cash",
            "backtest_buy_commission",
            "backtest_sell_commission",
            "backtest_stamp_duty",
            "backtest_min_commission",
            "backtest_slippage",
            "risk_max_order_position_pct",
            "risk_max_order_notional",
            "risk_max_daily_notional",
        ):
            cleaned[field] = float(raw)
        elif field == "paper_runner_interval_minutes":
            cleaned[field] = max(5, int(float(raw)))
        elif field in (
            "auto_execute_live",
            "i_understand_auto_live",
            "qmt_force_mock",
            "paper_runner_enabled",
        ):
            if isinstance(raw, bool):
                cleaned[field] = raw
            else:
                cleaned[field] = str(raw).strip().lower() in ("1", "true", "yes", "on")
        elif field in ("trade_mode", "ml_engine", "llm_provider"):
            cleaned[field] = str(raw).strip().lower()
        else:
            cleaned[field] = str(raw).strip()

    if "trade_mode" in cleaned and cleaned["trade_mode"] not in ("paper", "live"):
        raise ValueError("trade_mode 须为 paper 或 live")
    if "ml_engine" in cleaned and cleaned["ml_engine"] not in ("lightgbm", "xgboost"):
        raise ValueError("ml_engine 须为 lightgbm 或 xgboost")
    if "llm_provider" in cleaned and cleaned["llm_provider"] not in (
        "openai",
        "deepseek",
        "chatgpt",
    ):
        raise ValueError("llm_provider 无效")
    if "risk_max_order_position_pct" in cleaned:
        pct = cleaned["risk_max_order_position_pct"]
        if pct <= 0 or pct > 100:
            raise ValueError("risk_max_order_position_pct 须在 (0, 100] 之间")
    for key in (
        "risk_max_order_notional",
        "risk_max_daily_notional",
        "backtest_min_commission",
    ):
        if key in cleaned and cleaned[key] < 0:
            raise ValueError(f"{key} 不能为负")

    trial = current.model_dump()
    trial.update(cleaned)
    Settings(**trial)

    if cleaned:
        upsert_env(cleaned)
        get_settings.cache_clear()

    return public_settings()
