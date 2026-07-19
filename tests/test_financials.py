"""财务快照模型测试。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import FinancialSnapshot


@pytest.fixture()
def _db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_financial_snapshot_roundtrip(_db):
    db = Session(get_engine())
    row = FinancialSnapshot(
        symbol="600519.SH",
        table_name="Income",
        period="20231231",
        source="qmt",
        payload_json='{"revenue": 1}',
        fetched_at=datetime(2024, 4, 1, 12, 0, 0),
    )
    db.add(row)
    db.flush()
    assert row.id is not None
    db.rollback()
    db.close()


def test_mock_qmt_financials_returns_tables():
    from desk_market.qmt_financials import MockQmtFinancials

    src = MockQmtFinancials(
        data={
            "600519.SH": {
                "Income": [{"period": "20241231", "revenue": 1e11, "net_profit": 5e10}],
                "Pershareindex": [{"period": "20241231", "roe": 30.0, "eps": 50.0}],
            }
        }
    )
    out = src.get_financials("600519.SH", tables=["Income", "Pershareindex"])
    assert out["source"] == "qmt"
    assert out["tables"]["Income"][0]["net_profit"] == 5e10


def test_map_qmt_row_net_margin_prefers_ratio_over_net_profit():
    from desk_market.qmt_financials import _map_qmt_row

    row = _map_qmt_row(
        {
            "period": "20241231",
            "net_profit": 5e10,
            "net_margin": 25.5,
        }
    )
    assert row["net_profit"] == 5e10
    assert row["net_margin"] == 25.5


def test_map_qmt_row_net_margin_none_when_only_net_profit():
    from desk_market.qmt_financials import _map_qmt_row

    row = _map_qmt_row({"period": "20241231", "net_profit": 5e10})
    assert row["net_profit"] == 5e10
    assert row["net_margin"] is None


def test_map_qmt_row_balance_equity_maps_to_total_equity():
    from desk_market.qmt_financials import _map_qmt_row

    row = _map_qmt_row(
        {
            "period": "20241231",
            "tot_shrhldr_eqy_excl_min_int": 8e11,
        }
    )
    assert row["total_equity"] == 8e11


def test_fetch_akshare_financials_monkeypatch(monkeypatch):
    from desk_market import akshare_financials

    def fake_raw(code: str, years: int = 5):
        assert code == "600519"
        assert years == 5
        return {
            "Income": [{"period": "20241231", "revenue": 1e11, "net_profit": 5e10}],
            "Pershareindex": [{"period": "20241231", "roe": 28.0, "eps": 45.0}],
        }

    monkeypatch.setattr(akshare_financials, "_raw_fetch", fake_raw)
    out = akshare_financials.fetch_akshare_financials("600519")
    assert out["source"] == "akshare"
    assert out["symbol"] == "600519.SH"
    assert out["tables"]["Income"][0]["net_profit"] == 5e10
