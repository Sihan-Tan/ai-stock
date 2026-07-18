"""设置 API：读取与补丁持久化。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_common.settings_store import apply_settings_patch, public_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401


@pytest.fixture()
def _db(tmp_path, monkeypatch):
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    env_file = tmp_path / ".env"
    env_file.write_text("TRADE_MODE=paper\nML_ENGINE=lightgbm\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    yield env_file
    reset_engine()
    get_settings.cache_clear()


def test_public_settings_has_core_fields(_db):
    data = public_settings()
    assert data["trade_mode"] in ("paper", "live")
    assert "risk_max_order_position_pct" in data
    assert "backtest_stamp_duty" in data


def test_apply_patch_writes_env(_db):
    apply_settings_patch(
        {
            "trade_mode": "live",
            "risk_max_order_position_pct": 15,
            "risk_max_order_notional": 88888,
            "backtest_buy_commission": 0.0003,
        }
    )
    text = _db.read_text(encoding="utf-8")
    assert "TRADE_MODE=live" in text
    assert "RISK_MAX_ORDER_POSITION_PCT=15" in text
    assert "RISK_MAX_ORDER_NOTIONAL=88888" in text
    s = get_settings()
    assert s.trade_mode == "live"
    assert s.risk_max_order_position_pct == 15.0
