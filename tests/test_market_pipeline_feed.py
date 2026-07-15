"""DataFeed 默认前复权列，可切 hfq。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_market import MarketService


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_load_and_backtest_request_adj(_db):
    db = Session(get_engine())
    svc = MarketService(db)
    rows = []
    for i, d in enumerate([date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]):
        px = 10 + i
        rows.append(
            {
                "date": d,
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "volume": 1,
                "amount": 1,
                "open_hfq": px * 10,
                "high_hfq": px * 10,
                "low_hfq": px * 10,
                "close_hfq": px * 10,
                "volume_hfq": 1,
            }
        )
    svc.upsert_daily_bars("600519.SH", pd.DataFrame(rows))
    db.commit()
    df_q = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 10), adj="qfq")
    df_h = svc.load_daily_df("600519.SH", date(2024, 1, 1), date(2024, 1, 10), adj="hfq")
    assert float(df_q.iloc[0]["close"]) == 10.0
    assert float(df_h.iloc[0]["close"]) == 100.0

    from desk_common.contracts import BacktestRequest
    from desk_backtest import BacktraderRunner

    calls: list[str | None] = []
    orig = svc.load_daily_df

    def _wrap(*a, **k):
        calls.append(k.get("adj", a[3] if len(a) > 3 else None))
        return orig(*a, **k)

    svc.load_daily_df = _wrap  # type: ignore[method-assign]
    runner = BacktraderRunner(db)
    runner.market = svc
    runner.run(
        BacktestRequest(
            strategy_id="ma_cross",
            symbol="600519.SH",
            start=date(2024, 1, 2),
            end=date(2024, 1, 4),
            adj="hfq",
        )
    )
    assert "hfq" in calls
