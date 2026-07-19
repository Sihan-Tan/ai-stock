"""晨会进自选与执行质量。"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_broker import PaperBroker  # noqa: E402
from desk_broker.execution_quality import analyze_paper_execution  # noqa: E402
from desk_common.contracts import OrderIntent, Side  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_db import Base, get_engine, reset_engine  # noqa: E402
from desk_db.models import MorningStrongPick, WatchlistItem  # noqa: E402
from desk_morning_brief.bind import bind_morning_picks  # noqa: E402
from desk_review.attribution import simple_vs_buyhold  # noqa: E402
import desk_db.models  # noqa: F401, E402


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    session = Session(get_engine())
    yield session
    session.close()
    reset_engine()
    get_settings.cache_clear()


def test_bind_morning_picks(db: Session):
    today = date.today()
    db.add(
        MorningStrongPick(
            asof=today,
            pick_type="stock",
            code="600519.SH",
            name="贵州茅台",
            score=90.0,
            meta_json="{}",
        )
    )
    db.commit()
    out = bind_morning_picks(db, asof=today)
    assert out["count"] >= 1
    assert "600519.SH" in out["added"]
    from sqlalchemy import select

    row = db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == "600519.SH"))
    assert row is not None


def test_execution_quality_runs(db: Session):
    PaperBroker(db).place_order(
        OrderIntent(
            symbol="600000.SH",
            side=Side.BUY,
            qty=100,
            price=10.0,
            client_order_id=f"q-{uuid4().hex[:8]}",
            mode="paper",
        )
    )
    stats = analyze_paper_execution(db)
    assert stats["trades"] >= 1
    assert "configured_slip_bps" in stats
    assert "buy_count" in stats
    assert stats["buy_count"] >= 1


def test_attribution_empty(db: Session):
    out = simple_vs_buyhold(db)
    assert out["status"] == "empty"
    assert "暂无回测" in (out.get("message") or "")
