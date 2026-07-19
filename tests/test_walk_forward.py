"""Walk-Forward IS/OOS 比例计算与 KPI 写入。"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_backtest.walk_forward import is_oos_sharpe_ratio, run_walk_forward  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_db import Base, get_engine, reset_engine  # noqa: E402
from desk_market import MarketService  # noqa: E402
from desk_strategy import StrategyRegistry  # noqa: E402
import desk_db.models  # noqa: F401, E402
import desk_strategy.strategies  # noqa: F401, E402


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


def test_is_oos_ratio_math():
    assert abs(is_oos_sharpe_ratio(2.0, 1.4) - 0.7) < 1e-9
    assert is_oos_sharpe_ratio(0.0, 1.0) == 1.0
    assert is_oos_sharpe_ratio(-1.0, -0.5) == 0.0


def _seed_bars(db: Session, symbol: str = "600519.SH") -> None:
    svc = MarketService(db)
    today = date.today()
    price = 100.0
    rows = []
    for i in range(220, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        phase = (len(rows) // 20) % 2
        price *= 1.012 if phase == 0 else 0.988
        rows.append(
            {
                "date": d,
                "open": price * 0.99,
                "high": price * 1.01,
                "low": price * 0.98,
                "close": price,
                "volume": 1e6,
                "amount": price * 1e6,
                "open_hfq": price * 0.99,
                "high_hfq": price * 1.01,
                "low_hfq": price * 0.98,
                "close_hfq": price,
                "volume_hfq": 1e6,
            }
        )
    svc.upsert_daily_bars(symbol, pd.DataFrame(rows))
    db.commit()


def test_run_walk_forward_ok(db: Session):
    _seed_bars(db)
    out = run_walk_forward(db, strategy_id="ma_cross", symbol="600519.SH")
    assert out["status"] == "ok"
    assert "walk_forward_is_oos_ratio" in out
    assert out["walk_forward_is_oos_ratio"] >= 0


def test_apply_walk_forward_writes_kpi(db: Session):
    _seed_bars(db)
    reg = StrategyRegistry(db)
    reg.sync_python_to_db()
    db.commit()
    result = reg.apply_walk_forward("ma_cross", symbol="600519.SH")
    assert result["status"] == "ok"
    assert float(result["kpi"]["walk_forward_is_oos_ratio"]) >= 0
    assert "walk_forward_is_oos_ratio" in (result.get("kpi") or {})
