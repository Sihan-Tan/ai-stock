"""策略软删除 / 硬删除。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import StrategyRow
from desk_strategy import StrategyRegistry


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_soft_then_hard_delete(_db):
    """首次 archived，再次删库行；默认列表不含软删。"""
    db = Session(get_engine())
    db.add(
        StrategyRow(
            strategy_id="tmp_yaml_x",
            name="临时",
            source="yaml",
            version="v0.1",
            status="research",
            yaml_body="id: tmp_yaml_x\nname: 临时\n",
        )
    )
    db.commit()

    reg = StrategyRegistry(db)
    soft = reg.delete("tmp_yaml_x")
    assert soft == {"action": "soft", "strategy_id": "tmp_yaml_x"}
    visible_ids = {m.id for m in reg.list()}
    archived_ids = {m.id for m in reg.list(include_archived=True)}
    assert "tmp_yaml_x" not in visible_ids
    assert "tmp_yaml_x" in archived_ids
    row = db.scalar(select(StrategyRow).where(StrategyRow.strategy_id == "tmp_yaml_x"))
    assert row is not None and row.status == "archived"

    hard = reg.delete("tmp_yaml_x")
    assert hard == {"action": "hard", "strategy_id": "tmp_yaml_x"}
    assert db.scalar(select(StrategyRow).where(StrategyRow.strategy_id == "tmp_yaml_x")) is None
    assert "tmp_yaml_x" not in {m.id for m in reg.list(include_archived=True)}
    db.close()
