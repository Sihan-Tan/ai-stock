"""Paper Runner：策略 on_bar → PaperBroker 成交。"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_broker.paper_runner import PaperStrategyRunner  # noqa: E402
from desk_common.settings import get_settings  # noqa: E402
from desk_db import Base, get_engine, reset_engine  # noqa: E402
from desk_db.models import WatchlistItem  # noqa: E402
from desk_market import MarketService  # noqa: E402
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


def _seed_uptrend(db: Session, symbol: str = "600519.SH") -> None:
    """写入一段上涨日线，便于均线策略产生上下文。"""
    svc = MarketService(db)
    today = date.today()
    price = 100.0
    rows = []
    for i in range(80, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        price *= 1.01
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


def test_run_once_ma_cross_places_or_skips(db: Session):
    """有 K 线时 run_once 应返回结构化结果，且不抛错。"""
    _seed_uptrend(db)
    runner = PaperStrategyRunner(db)
    result = runner.run_once(strategy_id="ma_cross", symbol="600519.SH")
    assert result["strategy_id"] == "ma_cross"
    assert result["symbol"] == "600519.SH"
    assert "signals" in result
    assert "orders" in result
    assert result["status"] == "ok"
    assert result["last_price"] is not None


def test_run_once_alerts_when_order_filled(db: Session, monkeypatch: pytest.MonkeyPatch):
    """成交或拒绝时会调用告警（不依赖真实飞书）。"""
    calls: list[dict] = []

    def _capture(self, *, title: str, body: str, category: str, dedupe_key: str) -> None:
        calls.append(
            {"title": title, "body": body, "category": category, "dedupe_key": dedupe_key}
        )

    monkeypatch.setattr(PaperStrategyRunner, "_alert_paper", _capture)
    _seed_uptrend(db)
    # 晋升闸门默认 incubating 可能挡买；把策略标为 probation 以便有机会下单
    from desk_strategy import StrategyRegistry

    reg = StrategyRegistry(db)
    meta = reg.load("ma_cross")
    if meta and meta.meta:
        # 通过 ORM 更新 lifecycle
        from sqlalchemy import select

        from desk_db.models import StrategyRow

        row = db.scalar(
            select(StrategyRow)
            .where(StrategyRow.strategy_id == "ma_cross")
            .order_by(StrategyRow.id.desc())
        )
        if row is not None:
            row.lifecycle_stage = "probation"
            db.commit()

    result = PaperStrategyRunner(db).run_once(strategy_id="ma_cross", symbol="600519.SH")
    assert result["status"] == "ok"
    if result.get("orders"):
        assert any(c["category"] in ("paper", "risk") for c in calls)
        assert any("paper:" in c["dedupe_key"] or "reject:" in c["dedupe_key"] for c in calls)


def test_run_once_unknown_strategy(db: Session):
    """未知策略应返回 error。"""
    result = PaperStrategyRunner(db).run_once(strategy_id="no_such", symbol="600519.SH")
    assert result["status"] == "error"
    assert "not runnable" in result["message"]


def test_run_watchlist_empty(db: Session):
    """空自选应返回 count=0。"""
    out = PaperStrategyRunner(db).run_watchlist(strategy_id="ma_cross")
    assert out["status"] == "ok"
    assert out["count"] == 0


def test_run_watchlist_one_symbol(db: Session):
    """自选一只标的时可批量跑。"""
    _seed_uptrend(db)
    db.add(WatchlistItem(symbol="600519.SH", name="贵州茅台"))
    db.commit()
    out = PaperStrategyRunner(db).run_watchlist(strategy_id="ma_cross")
    assert out["count"] == 1
    assert out["results"][0]["status"] == "ok"
