"""策略生命周期 / KPI 评估。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
from desk_strategy import StrategyRegistry
from desk_strategy.lifecycle import (
    LifecycleStage,
    StrategyKPI,
    decide_next_stage,
    lifecycle_to_status,
)


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def client(_db):
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_decide_next_stage_rules():
    assert (
        decide_next_stage(
            LifecycleStage.INCUBATING,
            StrategyKPI(walk_forward_is_oos_ratio=0.8),
        )
        == LifecycleStage.PAPER
    )
    assert (
        decide_next_stage(
            LifecycleStage.PAPER,
            StrategyKPI(days_since_promotion=25, rolling_30d_return=0.02, rolling_30d_maxdd=0.02),
        )
        == LifecycleStage.PROBATION
    )
    # 孵化阶段大回撤不应直接退役
    assert (
        decide_next_stage(
            LifecycleStage.INCUBATING,
            StrategyKPI(rolling_30d_maxdd=0.35),
        )
        is None
    )
    assert (
        decide_next_stage(
            LifecycleStage.PRODUCTION,
            StrategyKPI(rolling_30d_maxdd=0.25),
        )
        == LifecycleStage.RETIRED
    )
    assert lifecycle_to_status(LifecycleStage.RETIRED) == "research"


def test_restore_archived_strategies(_db):
    db = get_session_factory()()
    try:
        reg = StrategyRegistry(db)
        reg.sync_python_to_db()
        sid = reg.list()[0].id
        reg.delete(sid)
        assert not any(m.id == sid for m in reg.list(include_archived=False))
        assert any(m.id == sid for m in reg.list(include_archived=True))
        n = reg.restore_visible_strategies()
        assert n >= 1
        assert any(m.id == sid for m in reg.list(include_archived=False))
    finally:
        db.close()


def test_evaluate_migrates_incubating(_db):
    db = get_session_factory()()
    try:
        reg = StrategyRegistry(db)
        reg.sync_python_to_db()
        rows = reg.list()
        assert rows
        sid = rows[0].id
        reg.set_stage(sid, "incubating", reason="测试重置")
        reg.update_kpi(sid, walk_forward_is_oos_ratio=0.85, rolling_30d_return=0.01)
        migrations = reg.evaluate_and_migrate(refresh_from_backtest=False)
        assert any(m["strategy_id"] == sid and m["to"] == "paper" for m in migrations)
        meta = next(m for m in reg.list() if m.id == sid)
        assert meta.lifecycle_stage == "paper"
        assert meta.capital_pct == 0.0
    finally:
        db.close()


def test_lifecycle_api(client):
    stages = client.get("/api/strategies/lifecycle/stages")
    assert stages.status_code == 200
    assert "incubating" in stages.json()["stages"]

    client.post("/api/strategies/sync-python")
    summary = client.get("/api/strategies/lifecycle/summary")
    assert summary.status_code == 200
    assert "total_capital" in summary.json()

    listed = client.get("/api/strategies").json()
    assert listed
    sid = listed[0]["id"]
    assert "lifecycle_stage" in listed[0]

    kpi = client.post(
        f"/api/strategies/{sid}/lifecycle/kpi",
        json={"walk_forward_is_oos_ratio": 0.9, "rolling_30d_return": 0.02},
    )
    assert kpi.status_code == 200

    stage = client.post(
        f"/api/strategies/{sid}/lifecycle/stage",
        json={"stage": "probation", "reason": "单测"},
    )
    assert stage.status_code == 200
    assert stage.json()["lifecycle_stage"] == "probation"
    assert stage.json()["capital_pct"] == pytest.approx(0.05)

    ev = client.post("/api/strategies/lifecycle/evaluate")
    assert ev.status_code == 200
    assert "migrations" in ev.json()
