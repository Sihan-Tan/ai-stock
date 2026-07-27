"""持仓建议：格式化、解析、编排。"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

from desk_db.models import PaperAccount, PaperPosition
from desk_positions_advice import advise_advice
from desk_positions_advice.format import append_advice_section
from desk_positions_advice.llm import generate_advice_llm, normalize_action, parse_advice_payload
from desk_positions_advice.positions import load_positions, truncate_positions


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    session = Session(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


def test_append_advice_section_empty_positions():
    base = "【尾盘选股】2026-07-27\n命中 1 只"
    advice = {
        "status": "empty",
        "source": "live",
        "section": "当前无持仓，跳过建议",
        "items": [],
    }
    out = append_advice_section(base, advice)
    assert "持仓建议（live）" in out
    assert "当前无持仓，跳过建议" in out
    assert out.startswith(base)


def test_normalize_action_closing_invalid():
    assert normalize_action("加仓", "closing") == ("持有", True)
    assert normalize_action("卖出", "closing") == ("卖出", False)


def test_normalize_action_morning():
    assert normalize_action("高抛低吸", "morning") == ("高抛低吸", False)
    assert normalize_action("低吸", "morning") == ("低吸", False)
    assert normalize_action("观望", "morning") == ("持有", True)


def test_truncate_positions_by_market_value():
    rows = [
        {"symbol": f"s{i}", "qty": 100, "cost": 10, "market_value": float(i), "pnl": 0}
        for i in range(25)
    ]
    out, truncated = truncate_positions(rows, limit=20)
    assert truncated is True
    assert len(out) == 20
    assert out[0]["symbol"] == "s24"


def test_load_paper_positions(db: Session):
    acc = PaperAccount(name="default", cash=1_000_000, equity=1_000_000)
    db.add(acc)
    db.flush()
    db.add(PaperPosition(account_id=acc.id, symbol="600000.SH", qty=100, cost=10.0))
    db.commit()
    loaded = load_positions(db, "paper")
    assert loaded["ok"] is True
    assert loaded["source"] == "paper"
    assert any(p["symbol"] == "600000.SH" for p in loaded["positions"])


from desk_positions_advice.rules import rule_candidates


def test_rule_candidates_closing_sell_on_big_drop():
    positions = [
        {
            "symbol": "600000.SH",
            "qty": 100,
            "cost": 10,
            "last_price": 8.5,
            "pnl": -150,
            "day_chg_pct": -0.06,
        }
    ]
    out = rule_candidates(positions, session_kind="closing")
    assert out[0]["symbol"] == "600000.SH"
    assert out[0]["action"] == "卖出"


def test_rule_candidates_exception_safe(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    # 若 rules 内部调用辅助失败，service 层会吞；此处保证单函数对坏数据不炸
    out = rule_candidates([{"symbol": "x"}], session_kind="morning")
    assert isinstance(out, list)


def test_parse_advice_payload_ok():
    raw = json.dumps(
        {
            "items": [{"symbol": "600000.SH", "action": "卖出", "reason": "走弱"}],
            "market_note": "情绪偏弱",
        },
        ensure_ascii=False,
    )
    parsed = parse_advice_payload(raw, "closing")
    assert parsed is not None
    assert parsed["items"][0]["action"] == "卖出"


def test_generate_advice_llm_mock():
    facts = {"positions": [{"symbol": "600000.SH"}], "session_kind": "closing"}

    def fake(system: str, user: str) -> str:
        return json.dumps(
            {
                "items": [
                    {"symbol": "600000.SH", "action": "持有", "reason": "ok"},
                ]
            },
            ensure_ascii=False,
        )

    out = generate_advice_llm(facts, session_kind="closing", llm_call=fake)
    assert out["status"] == "ok"
    assert out["items"][0]["symbol"] == "600000.SH"


def test_generate_advice_llm_error():
    def boom(system: str, user: str) -> str:
        raise RuntimeError("network")

    out = generate_advice_llm({}, session_kind="closing", llm_call=boom)
    assert out["status"] == "error"


def test_advise_advice_disabled(db, monkeypatch):
    monkeypatch.setattr(
        "desk_positions_advice.service.get_settings",
        lambda: type("S", (), {
            "positions_advice_enabled": False,
            "positions_advice_mode": "llm",
            "positions_advice_source": "live",
            "llm_api_key": "x",
        })(),
    )
    out = advise_advice(db, session_kind="closing", asof=date(2026, 7, 27))
    assert out["status"] == "disabled"


def test_advise_advice_empty_positions(db, monkeypatch):
    monkeypatch.setattr(
        "desk_positions_advice.service.get_settings",
        lambda: type("S", (), {
            "positions_advice_enabled": True,
            "positions_advice_mode": "llm",
            "positions_advice_source": "live",
            "llm_api_key": "x",
        })(),
    )
    monkeypatch.setattr(
        "desk_positions_advice.service.load_positions",
        lambda db, source: {"ok": True, "source": source, "positions": []},
    )
    out = advise_advice(db, session_kind="closing", asof=date(2026, 7, 27))
    assert out["status"] == "empty"
    assert "无持仓" in out["section"]


def test_advise_advice_llm_ok(db, monkeypatch):
    monkeypatch.setattr(
        "desk_positions_advice.service.get_settings",
        lambda: type("S", (), {
            "positions_advice_enabled": True,
            "positions_advice_mode": "llm",
            "positions_advice_source": "paper",
            "llm_api_key": "x",
        })(),
    )
    monkeypatch.setattr(
        "desk_positions_advice.service.load_positions",
        lambda db, source: {
            "ok": True,
            "source": "paper",
            "positions": [
                {
                    "symbol": "600000.SH",
                    "qty": 100,
                    "cost": 10,
                    "last_price": 11,
                    "market_value": 1100,
                    "pnl": 100,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "desk_positions_advice.service.generate_advice_llm",
        lambda facts, session_kind, llm_call=None: {
            "status": "ok",
            "items": [{"symbol": "600000.SH", "action": "持有", "reason": "稳"}],
            "market_note": None,
        },
    )
    out = advise_advice(db, session_kind="closing", asof=date(2026, 7, 27), picks=[])
    assert out["status"] == "ok"
    assert out["items"][0]["action"] == "持有"
