"""应用设置读写。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_common.settings_store import apply_settings_patch, public_settings
from desk_db import get_db

router = APIRouter(prefix="/settings")


class SettingsPatch(BaseModel):
    """设置补丁；未传或密钥留空表示不修改。"""

    trade_mode: str | None = None
    auto_execute_live: bool | None = None
    i_understand_auto_live: bool | None = None
    ml_engine: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    feishu_webhook_url: str | None = None
    feishu_sign_secret: str | None = None
    qmt_userdata_path: str | None = None
    qmt_account_id: str | None = None
    qmt_force_mock: bool | None = None
    paper_initial_cash: float | None = None
    paper_default_strategy_id: str | None = None
    paper_runner_enabled: bool | None = None
    paper_runner_strategy_id: str | None = None
    paper_runner_interval_minutes: int | None = None
    backtest_buy_commission: float | None = None
    backtest_sell_commission: float | None = None
    backtest_stamp_duty: float | None = None
    backtest_min_commission: float | None = None
    backtest_slippage: float | None = None
    risk_max_order_position_pct: float | None = None
    risk_max_order_notional: float | None = None
    risk_max_daily_notional: float | None = None
    risk_max_positions: int | None = None
    risk_armed: bool | None = None
    risk_kill_switch: bool | None = None
    risk_whitelist: str | None = None


@router.get("")
def get_app_settings() -> dict[str, Any]:
    """读取当前配置（密钥脱敏）。"""
    return public_settings()


@router.put("")
def put_app_settings(body: SettingsPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    更新配置并写入 .env，同步风控限额到内存网关。

    @param body: 设置补丁
    """
    patch = body.model_dump(exclude_none=True)
    try:
        result = apply_settings_patch(patch)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"保存失败: {exc}") from exc

    # 同步 BrokerGateway 限额（若已初始化）
    try:
        from app.routes.broker import _GATE

        if _GATE is not None:
            _GATE.risk.apply_from_settings()
    except Exception:  # noqa: BLE001
        pass

    return result
