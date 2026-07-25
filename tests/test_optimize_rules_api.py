"""POST /api/strategies/optimize-rules 校验与网格上限。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

CROSS_ONLY_YAML = {
    "id": "opt_cross_only",
    "name": "cross only",
    "kind": "factor_rules",
    "buy": {
        "combine": "all",
        "conditions": [
            {
                "op": "cross_up",
                "left": {"factor": "CLOSE"},
                "right": {"factor": "SMA_20"},
            }
        ],
    },
    "sell": {
        "combine": "any",
        "conditions": [
            {
                "op": "cross_down",
                "left": {"factor": "CLOSE"},
                "right": {"factor": "SMA_20"},
            }
        ],
    },
}

CONST_COMPARE_YAML = {
    "id": "opt_const",
    "name": "ml threshold",
    "kind": "factor_rules",
    "params": {"position_pct": 100, "max_hold_bars": 0},
    "buy": {
        "combine": "all",
        "conditions": [
            {"op": "gt", "left": {"factor": "ml:score"}, "right": {"const": 0.6}}
        ],
    },
    "sell": {
        "combine": "any",
        "conditions": [
            {"op": "lt", "left": {"factor": "ml:score"}, "right": {"const": 0.4}}
        ],
    },
}


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch):
    """内存库 Session。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield Session(bind=get_engine())
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def api_client(db: Session):
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


def _payload(**overrides):
    base = {
        "symbol": "600519.SH",
        "start": "2024-01-01",
        "end": "2024-06-30",
        "yaml_body": CROSS_ONLY_YAML,
    }
    base.update(overrides)
    return base


def test_optimize_rules_no_const_compare_400(api_client: TestClient):
    """仅 cross 条件、无可优化阈值 → 400。"""
    r = api_client.post("/api/strategies/optimize-rules", json=_payload())
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "无可优化" in detail


def test_optimize_rules_grid_too_large_400(api_client: TestClient):
    """网格组合超过 200 → 400。"""
    n = 11
    buy_grid = [0.5 + i * 0.01 for i in range(n)]
    sell_grid = [0.3 + i * 0.01 for i in range(n)]
    assert n * n * 2 > 200
    r = api_client.post(
        "/api/strategies/optimize-rules",
        json=_payload(
            yaml_body=CONST_COMPARE_YAML,
            buy_grid=buy_grid,
            sell_grid=sell_grid,
            position_pcts=[50, 100],
            max_hold_bars_list=[0],
        ),
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "200" in detail
