"""市场同步配置加载。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from desk_common.settings import get_settings
from desk_common.symbols import normalize_symbol

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _dotenv_paths() -> list[Path]:
    """
    候选 `.env` 路径：仓库根目录与工作目录。

    @returns: 去重后的路径列表
    """
    paths: list[Path] = []
    for candidate in (_REPO_ROOT / ".env", Path.cwd() / ".env"):
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _key_in_dotenv(key: str, dotenv_path: Path) -> bool:
    """
    判断 `.env` 文件中是否显式设置了指定键。

    @param key: 环境变量名
    @param dotenv_path: `.env` 文件路径
    @returns: 键存在且非注释行时为 True
    """
    if not dotenv_path.is_file():
        return False
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].strip()
        if "=" not in stripped:
            continue
        name, _ = stripped.split("=", 1)
        if name.strip() == key:
            return True
    return False


def _explicit_setting(key: str) -> bool:
    """
    判断配置项是否由进程环境或 `.env` 显式覆盖。

    pydantic-settings 从 `.env` 加载值但不会写入 `os.environ`；
    本函数用于区分「显式覆盖」与「字段默认值」。

    @param key: 环境变量名（如 `MARKET_DAILY_START`）
    @returns: 进程环境或任一候选 `.env` 中存在该键时为 True
    """
    if key in os.environ:
        return True
    return any(_key_in_dotenv(key, path) for path in _dotenv_paths())


def _resolve_config_path(path_str: str) -> Path:
    """
    将配置路径解析为绝对路径。

    @param path_str: 相对或绝对路径
    @returns: 绝对 Path
    """
    path = Path(path_str)
    if path.is_absolute():
        return path
    return _REPO_ROOT / path


@dataclass
class MarketSyncConfig:
    """
    市场同步任务配置（YAML + Settings 合并）。

    @property daily_start_date: 历史回填下界
    @property incremental_days: 日终增量近 N 日
    @property batch_size: 回填批大小
    @property jobs: 调度 job 默认参数
    """

    daily_start_date: date
    incremental_days: int
    batch_size: int
    jobs: dict[str, Any]


def load_market_sync_config() -> MarketSyncConfig:
    """
    加载 MarketSyncConfig：YAML 为底，Settings 环境变量覆盖。

    `MARKET_DAILY_START` 始终优先于 YAML 中的 `daily_start_date`。

    @returns: 合并后的配置
    """
    settings = get_settings()
    yaml_path = _resolve_config_path(settings.market_sync_yaml)
    raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

    daily_start_str = (
        settings.market_daily_start
        if _explicit_setting("MARKET_DAILY_START")
        else str(raw.get("daily_start_date", settings.market_daily_start))
    )
    daily_start = date.fromisoformat(daily_start_str)
    incremental_days = (
        settings.market_incremental_days
        if _explicit_setting("MARKET_INCREMENTAL_DAYS")
        else int(raw.get("incremental_days", settings.market_incremental_days))
    )
    batch_size = (
        settings.market_batch_size
        if _explicit_setting("MARKET_BATCH_SIZE")
        else int(raw.get("batch_size", settings.market_batch_size))
    )
    jobs = dict(raw.get("jobs") or {})

    return MarketSyncConfig(
        daily_start_date=daily_start,
        incremental_days=incremental_days,
        batch_size=batch_size,
        jobs=jobs,
    )


def load_indices() -> list[str]:
    """
    加载指数 symbol 列表。

    @returns: 规范化后的 symbol 列表
    """
    settings = get_settings()
    yaml_path = _resolve_config_path(settings.market_indices_yaml)
    raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    indices = raw.get("indices") or []
    return [
        normalize_symbol(str(item["symbol"]))
        for item in indices
        if isinstance(item, dict) and item.get("symbol")
    ]
