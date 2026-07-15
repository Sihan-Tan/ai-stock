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
    ml_engine: Literal["lightgbm", "xgboost"] = "lightgbm"

    llm_provider: Literal["openai", "deepseek", "chatgpt"] = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    feishu_webhook_url: str = ""
    feishu_sign_secret: str = ""

    qmt_userdata_path: str = r"C:\QMT\userdata_mini"
    qmt_account_id: str = ""

    paper_initial_cash: float = 1_000_000.0
    skills_dir: str = "skills"

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
