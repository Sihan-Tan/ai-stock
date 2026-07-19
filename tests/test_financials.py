"""财务快照模型测试。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
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
    try:
        from app.routes import broker as broker_routes

        broker_routes._GATE = None
    except Exception:  # noqa: BLE001
        pass
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


def test_ai_financials_endpoint(client, monkeypatch):
    """GET /api/ai/financials/{symbol} 返回 FinancialService 结果。"""
    from desk_market.financials import FinancialService

    def fake_get_financials(self, symbol, years=5):
        assert symbol in ("600519", "600519.SH")
        assert years == 3
        return {
            "symbol": "600519.SH",
            "source": "test",
            "metrics": [{"period": "20241231", "roe": 30.0}],
        }

    monkeypatch.setattr(FinancialService, "get_financials", fake_get_financials)
    r = client.get("/api/ai/financials/600519", params={"years": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "600519.SH"
    assert body["source"] == "test"
    assert body["metrics"][0]["roe"] == 30.0


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


def test_financial_service_uses_cache(_db):
    import json

    from desk_market.financials import FinancialService
    from desk_market.qmt_financials import MockQmtFinancials

    db = Session(get_engine())
    db.add(
        FinancialSnapshot(
            symbol="600519.SH",
            table_name="Abstract",
            period="20241231",
            source="qmt",
            payload_json=json.dumps({"roe": 31.0, "period": "20241231"}),
            fetched_at=datetime.utcnow(),
        )
    )
    db.flush()
    called = {"n": 0}

    class Boom(MockQmtFinancials):
        def get_financials(self, *a, **k):
            called["n"] += 1
            raise AssertionError("should not call")

    svc = FinancialService(
        db,
        qmt=Boom(),
        akshare_fetch=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")),
    )
    out = svc.get_financials("600519", years=5)
    assert out["source"] == "qmt"
    assert called["n"] == 0
    assert any(r.get("roe") == 31.0 for r in out["metrics"])
    db.close()


def test_financial_service_fallback_akshare(_db):
    from desk_market.financials import FinancialService
    from desk_market.qmt_financials import MockQmtFinancials

    def fake_ak(symbol, years=5):
        return {
            "source": "akshare",
            "symbol": "600519.SH",
            "tables": {"Abstract": [{"period": "20241231", "roe": 28.0}]},
        }

    db = Session(get_engine())
    svc = FinancialService(
        db,
        qmt=MockQmtFinancials(fail=True),
        akshare_fetch=fake_ak,
        ttl_days=7,
    )
    out = svc.get_financials("600519.SH")
    assert out["source"] == "akshare"
    assert out["metrics"][0]["roe"] == 28.0
    db.close()


def test_financial_service_both_fail(_db):
    from desk_market.financials import FinancialService
    from desk_market.qmt_financials import MockQmtFinancials

    db = Session(get_engine())
    svc = FinancialService(
        db,
        qmt=MockQmtFinancials(fail=True),
        akshare_fetch=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")),
    )
    out = svc.get_financials("600519.SH")
    assert "error" in out
    db.close()


def test_financial_service_peer_compare(_db):
    from desk_market.financials import FinancialService
    from desk_market.qmt_financials import MockQmtFinancials

    def fake_ak(symbol, years=5):
        from desk_common.symbols import normalize_symbol

        sym = normalize_symbol(symbol)
        if sym == "999999.SH":
            raise RuntimeError("missing")
        roe = 30.0 if sym == "600519.SH" else 18.0
        return {
            "source": "akshare",
            "symbol": sym,
            "tables": {"Abstract": [{"period": "20241231", "roe": roe, "eps": 10.0}]},
        }

    db = Session(get_engine())
    svc = FinancialService(
        db,
        qmt=MockQmtFinancials(fail=True),
        akshare_fetch=fake_ak,
    )
    out = svc.peer_compare(["600519.SH", "000858.SZ", "999999.SH"])
    assert "rows" in out or "metrics" in out or "table" in out
    assert "999999.SH" in out.get("missing", [])
    latest = out.get("rows") or out.get("table") or out.get("metrics") or []
    symbols = {r.get("symbol") for r in latest}
    assert "600519.SH" in symbols
    assert "000858.SZ" in symbols
    db.close()


def test_financial_service_get_valuation(_db):
    from desk_market import MarketService
    from desk_market.financials import FinancialService
    from desk_market.qmt_financials import MockQmtFinancials

    db = Session(get_engine())
    market = MarketService(db)
    market.upsert_quote("600519.SH", "贵州茅台", 1500.0, 0.0, 0.0)

    def fake_ak(symbol, years=5):
        return {
            "source": "akshare",
            "symbol": "600519.SH",
            "tables": {
                "Abstract": [
                    {"period": "20241231", "roe": 30.0, "eps": 50.0, "bps": 100.0},
                ]
            },
        }

    svc = FinancialService(
        db,
        qmt=MockQmtFinancials(fail=True),
        akshare_fetch=fake_ak,
        market=market,
    )
    out = svc.get_valuation("600519.SH")
    assert out["price"] == 1500.0
    assert out["pe"] == 30.0
    assert out["pb"] == 15.0
    assert out.get("pe_percentile") is None
    assert "note" in out
    db.close()
