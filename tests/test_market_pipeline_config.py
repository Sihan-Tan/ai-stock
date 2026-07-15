"""MarketSyncConfig 加载与 Settings 覆盖。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from desk_common.settings import get_settings
from desk_market.config import load_indices, load_market_sync_config


def test_load_indices_yaml(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "indices.yaml"
    cfg.write_text(
        "indices:\n  - symbol: 000300.SH\n    name: 沪深300\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_INDICES_YAML", str(cfg))
    get_settings.cache_clear()
    symbols = load_indices()
    assert "000300.SH" in symbols


def test_daily_start_date_from_yaml_when_env_unset(monkeypatch, tmp_path: Path):
    """YAML daily_start_date 在无 MARKET_DAILY_START 时应生效（非 Settings 默认值）。"""
    sync = tmp_path / "sync.yaml"
    sync.write_text(
        "daily_start_date: '2015-01-01'\nincremental_days: 2\nbatch_size: 50\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_SYNC_YAML", str(sync))
    monkeypatch.delenv("MARKET_DAILY_START", raising=False)
    get_settings.cache_clear()
    cfg = load_market_sync_config()
    assert cfg.daily_start_date == date(2015, 1, 1)


def test_daily_start_date_default_and_env_override(monkeypatch, tmp_path: Path):
    sync = tmp_path / "sync.yaml"
    sync.write_text(
        "daily_start_date: '2018-01-01'\nincremental_days: 2\nbatch_size: 50\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_SYNC_YAML", str(sync))
    monkeypatch.delenv("MARKET_DAILY_START", raising=False)
    get_settings.cache_clear()
    cfg = load_market_sync_config()
    assert cfg.daily_start_date == date(2018, 1, 1)
    assert cfg.incremental_days == 2

    monkeypatch.setenv("MARKET_DAILY_START", "2020-06-01")
    get_settings.cache_clear()
    cfg2 = load_market_sync_config()
    assert cfg2.daily_start_date == date(2020, 6, 1)
