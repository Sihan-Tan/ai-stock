"""应用配置（环境变量 / .env）。"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局 Settings。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://desk:desk@localhost:5432/desk"
    """Postgres/MySQL 连接超时（秒），避免启动与探测长时间卡住。"""
    db_connect_timeout: int = 3
    trade_mode: Literal["paper", "live"] = "paper"
    """实盘是否自动成交；False 时进入审批队列。"""
    auto_execute_live: bool = False
    """确认理解自动实盘风险；与 auto_execute_live 同时为 True 才可自动真单/模拟实盘成交。"""
    i_understand_auto_live: bool = False
    ml_engine: Literal["lightgbm", "xgboost"] = "lightgbm"

    llm_provider: Literal["openai", "deepseek", "chatgpt"] = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    feishu_webhook_url: str = ""
    feishu_sign_secret: str = ""

    qmt_userdata_path: str = r"C:\QMT\userdata_mini"
    qmt_account_id: str = ""
    """为 True 时即使双开关打开也不发真单，强制 Mock（CI/无柜台默认）。"""
    qmt_force_mock: bool = True

    paper_initial_cash: float = 1_000_000.0
    """纸交易买入手动单缺省策略（生命周期闸门用）。"""
    paper_default_strategy_id: str = "ma_cross"
    """是否启用 Paper Runner 定时扫描自选。"""
    paper_runner_enabled: bool = False
    """定时 Runner 使用的策略 ID。"""
    paper_runner_strategy_id: str = "ma_cross"
    """连续竞价时段扫描间隔（分钟，≥5）。"""
    paper_runner_interval_minutes: int = 30
    skills_dir: str = "skills"

    # 回测费用（A 股近似；均在 .env 配置）
    backtest_buy_commission: float = 0.00025
    """买入佣金率（成交额比例）。"""
    backtest_sell_commission: float = 0.00025
    """卖出佣金率（成交额比例，不含印花税）。"""
    backtest_stamp_duty: float = 0.001
    """印花税税率（仅卖出）。"""
    backtest_min_commission: float = 5.0
    """单笔佣金最低收费（元）；印花税不参与保底。"""
    backtest_slippage: float = 0.001
    """回测滑点（成交价比例）。"""

    # 交易限额与实盘闸门（下单风控，唯一来源）
    risk_max_order_position_pct: float = 10.0
    """单笔最大仓位：占总权益百分比（0–100，如 10 表示 10%）。"""
    risk_max_order_notional: float = 50_000.0
    """单笔最大金额（元）。"""
    risk_max_daily_notional: float = 200_000.0
    """单日累计最大金额（元）。"""
    risk_max_positions: int = 4
    """最多持仓股票只数；0 表示不限制。买入新标的时校验。"""
    risk_armed: bool = False
    """实盘 ARM：未开启时拒绝 live 下单。"""
    risk_kill_switch: bool = False
    """Kill Switch：开启后拒绝一切 live 下单。"""
    risk_whitelist: str = ""
    """实盘白名单，逗号分隔代码；空=不限制标的。"""

    market_daily_start: str = "2018-01-01"
    market_incremental_days: int = 3
    market_batch_size: int = 100
    market_sync_yaml: str = "configs/market/sync.yaml"
    market_indices_yaml: str = "configs/market/indices.yaml"
    market_scheduler_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """获取单例 Settings。"""
    return Settings()
