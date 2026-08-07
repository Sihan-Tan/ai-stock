"""投研精选：JSON 解析、过滤 TopN、跳过失败、同日覆盖。"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import ClosingPick, MorningStrongPick, ResearchPick, TradeCalendar


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch):
    """内存库 Session，对齐 closing / feishu 测试。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    monkeypatch.setenv("RESEARCH_REFINE_TOP_N", "5")
    monkeypatch.setenv("RESEARCH_REFINE_MIN_CONFIDENCE", "70")
    monkeypatch.setenv("RESEARCH_REFINE_MAX_CANDIDATES", "15")
    monkeypatch.setenv("RESEARCH_REFINE_AUTO", "false")
    get_settings.cache_clear()
    session = Session(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


@pytest.fixture()
def api_client(db: Session):
    """FastAPI TestClient，复用内存库（与 test_closing_api 一致）。"""
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


def _seed_trade_day(db: Session, day: date | None = None) -> date:
    asof = day or date(2026, 7, 24)
    db.add(TradeCalendar(cal_date=asof, is_open=True, note=""))
    db.commit()
    return asof


def test_morning_latest_includes_research_picks_key(db: Session, api_client: TestClient):
    """GET /api/morning/latest 响应含 research_picks 字段。"""
    asof = _seed_trade_day(db)
    r = api_client.get("/api/morning/latest", params={"asof": asof.isoformat()})
    assert r.status_code == 200
    data = r.json()
    assert "research_picks" in data
    assert data["research_picks"] == []


def test_parse_score_payload_valid():
    from desk_ai.refine import parse_score_payload

    payload = (
        '{"symbol":"600519.SH","score":88,"confidence":90,"rationale":"ok",'
        '"buy_low":1600,"buy_high":1650,"target_low":1750,"target_high":1850,"stop_loss":1550}'
    )
    out = parse_score_payload(payload, "600519.SH")
    assert out is not None
    assert out["score"] == 88 and out["confidence"] == 90
    assert out["buy_low"] == 1600 and out["buy_high"] == 1650
    assert out["target_low"] == 1750 and out["stop_loss"] == 1550

    fenced = parse_score_payload(
        '```json\n{"symbol":"600519.SH","score":70,"confidence":80,"rationale":"fence",'
        '"buy_range":[10,11],"target_range":[12,13],"stop_loss":9.5}\n```',
        "600519.SH",
    )
    assert fenced is not None
    assert fenced["score"] == 70
    assert fenced["buy_low"] == 10 and fenced["target_high"] == 13


def test_parse_score_payload_invalid_skips():
    from desk_ai.refine import parse_score_payload

    assert parse_score_payload("not-json", "600519.SH") is None
    assert parse_score_payload('{"score":120,"confidence":50}', "x") is None
    assert parse_score_payload('{"score":50,"confidence":-1}', "x") is None
    # 缺价格计划
    assert (
        parse_score_payload(
            '{"symbol":"x","score":80,"confidence":80,"rationale":"no-price"}',
            "600519.SH",
        )
        is None
    )


def test_parse_score_payload_list_and_feishu_body():
    """批量 JSON 解析与飞书全量正文。"""
    from desk_common.contracts import ResearchPickItem
    from desk_ai.refine import format_research_feishu_body, parse_score_payload_list

    text = """```json
[
  {"symbol":"600519.SH","score":90,"confidence":88,"rationale":"a",
   "buy_low":1600,"buy_high":1650,"target_low":1700,"target_high":1800,"stop_loss":1550},
  {"symbol":"000001.SZ","score":70,"confidence":75,"rationale":"b",
   "buy_range":[10,11],"target_range":[12,13],"stop_loss":9.5}
]
```"""
    mapped = parse_score_payload_list(text, ["600519.SH", "000001.SZ"])
    assert set(mapped) == {"600519.SH", "000001.SZ"}
    assert mapped["000001.SZ"]["buy_low"] == 10

    body = format_research_feishu_body(
        date(2026, 7, 25),
        "morning",
        [
            ResearchPickItem(
                symbol="600519.SH",
                name="茅台",
                score=90,
                confidence=88,
                rationale="强势",
                rank=1,
                buy_low=1600,
                buy_high=1650,
                target_low=1700,
                target_high=1800,
                stop_loss=1550,
            )
        ],
        errors=["x:skip"],
    )
    assert "买入 1600.00–1650.00" in body
    assert "止损 1550.00" in body
    assert "理由：强势" in body
    assert "异常：x:skip" in body


def _price_plan(symbol: str, **extra: object) -> dict:
    """测试用完整评分载荷（含必填价格）。"""
    base = {
        "symbol": symbol,
        "score": 88,
        "confidence": 90,
        "rationale": "ok",
        "buy_low": 10.0,
        "buy_high": 11.0,
        "target_low": 12.0,
        "target_high": 13.0,
        "stop_loss": 9.0,
    }
    base.update(extra)
    return base


def _seed_morning_stocks(db: Session, asof: date) -> None:
    """插入 3 只 morning stock picks。"""
    rows = [
        ("600519.SH", "茅台", 90.0),
        ("000001.SZ", "平安", 80.0),
        ("300750.SZ", "宁德", 70.0),
    ]
    for code, name, score in rows:
        db.add(
            MorningStrongPick(
                asof=asof,
                pick_type="stock",
                code=code,
                name=name,
                score=score,
                meta_json="{}",
            )
        )
    db.commit()


def test_refine_filters_by_confidence_and_top_n(db: Session):
    from desk_ai.refine import ResearchRefineService

    # 周五，避免非交易日回退导致查不到候选
    asof = date(2026, 7, 24)
    _seed_morning_stocks(db, asof)

    scores = {
        "600519.SH": _price_plan("600519.SH", score=95, confidence=90, rationale="a"),
        "000001.SZ": _price_plan("000001.SZ", score=85, confidence=75, rationale="b"),
        "300750.SZ": _price_plan("300750.SZ", score=99, confidence=60, rationale="c"),
    }

    def scorer(symbol: str, name: str, context: dict):
        return scores.get(symbol)

    report = ResearchRefineService(db, scorer=scorer).run(
        "morning",
        asof,
        top_n=2,
        min_confidence=70,
    )
    assert report.candidates_evaluated == 3
    assert len(report.picks) == 2
    assert all(p.confidence >= 70 for p in report.picks)
    assert [p.symbol for p in report.picks] == ["600519.SH", "000001.SZ"]
    assert [p.rank for p in report.picks] == [1, 2]
    assert report.picks[0].score >= report.picks[1].score


def test_refine_skips_scorer_failure(db: Session):
    from desk_ai.refine import ResearchRefineService

    asof = date(2026, 7, 24)
    _seed_morning_stocks(db, asof)

    def scorer(symbol: str, name: str, context: dict):
        if symbol == "000001.SZ":
            raise RuntimeError("boom")
        if symbol == "300750.SZ":
            return None
        return _price_plan(symbol, score=88, confidence=90, rationale="ok")

    report = ResearchRefineService(db, scorer=scorer).run("morning", asof, top_n=5, min_confidence=70)
    assert len(report.picks) == 1
    assert report.picks[0].symbol == "600519.SH"
    assert any("000001" in e or "boom" in e for e in report.errors)


def test_refine_overwrite_same_asof_source(db: Session):
    from desk_ai.refine import ResearchRefineService, list_research_picks

    asof = date(2026, 7, 24)
    _seed_morning_stocks(db, asof)

    def scorer_all(symbol: str, name: str, context: dict):
        return _price_plan(symbol, score=80, confidence=80, rationale="v1")

    ResearchRefineService(db, scorer=scorer_all).run("morning", asof, top_n=5, min_confidence=70)
    first = list_research_picks(db, asof, "morning")
    assert len(first) == 3
    assert first[0]["buy_low"] is not None and first[0]["stop_loss"] is not None

    def scorer_one(symbol: str, name: str, context: dict):
        if symbol != "600519.SH":
            return None
        return _price_plan(symbol, score=91, confidence=95, rationale="v2")

    ResearchRefineService(db, scorer=scorer_one).run("morning", asof, top_n=5, min_confidence=70)
    second = list_research_picks(db, asof, "morning")
    assert len(second) == 1
    assert second[0]["symbol"] == "600519.SH"
    assert second[0]["rationale"] == "v2"

    rows = db.scalars(
        select(ResearchPick).where(ResearchPick.asof == asof, ResearchPick.source == "morning")
    ).all()
    assert len(rows) == 1


def test_missing_llm_key_does_not_clear_existing_picks(
    db: Session, monkeypatch: pytest.MonkeyPatch
):
    """无 Key 且走默认 scorer 时：返回 llm_api_key_missing，且不删除已有精选。"""
    from desk_ai.refine import ResearchRefineService, list_research_picks

    asof = date(2026, 7, 24)
    _seed_morning_stocks(db, asof)
    db.add(
        ResearchPick(
            asof=asof,
            source="morning",
            symbol="600519.SH",
            name="茅台",
            score=88.0,
            confidence=90.0,
            rationale="keep-me",
            rank=1,
            meta_json="{}",
        )
    )
    db.commit()

    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()

    report = ResearchRefineService(db).run("morning", asof)
    assert report.errors == ["llm_api_key_missing"]
    assert report.picks == []

    remaining = list_research_picks(db, asof, "morning")
    assert len(remaining) == 1
    assert remaining[0]["rationale"] == "keep-me"


def test_all_scorer_failures_do_not_clear_existing_picks(db: Session):
    """候选均评分失败时保留旧精选。"""
    from desk_ai.refine import ResearchRefineService, list_research_picks

    asof = date(2026, 7, 24)
    _seed_morning_stocks(db, asof)
    db.add(
        ResearchPick(
            asof=asof,
            source="morning",
            symbol="600519.SH",
            name="茅台",
            score=88.0,
            confidence=90.0,
            rationale="keep-me",
            rank=1,
            meta_json="{}",
        )
    )
    db.commit()

    def scorer_none(symbol: str, name: str, context: dict):
        return None

    report = ResearchRefineService(db, scorer=scorer_none).run(
        "morning", asof, top_n=5, min_confidence=70
    )
    assert report.picks == []
    assert report.errors
    remaining = list_research_picks(db, asof, "morning")
    assert len(remaining) == 1
    assert remaining[0]["rationale"] == "keep-me"


def test_maybe_auto_refine_respects_flag(db: Session, monkeypatch: pytest.MonkeyPatch):
    from desk_ai import refine as refine_mod

    calls: list[tuple] = []

    class Spy:
        def __init__(self, db, scorer=None):
            pass

        def run(self, source, asof=None, *, top_n=None, min_confidence=None):
            calls.append((source, asof))
            return None

    monkeypatch.setattr(refine_mod, "ResearchRefineService", Spy)
    monkeypatch.setenv("RESEARCH_REFINE_AUTO", "false")
    get_settings.cache_clear()
    refine_mod.maybe_auto_refine(db, "morning", date(2026, 7, 25))
    assert calls == []

    monkeypatch.setenv("RESEARCH_REFINE_AUTO", "true")
    monkeypatch.setenv("LLM_API_KEY", "x")
    get_settings.cache_clear()
    refine_mod.maybe_auto_refine(db, "morning", date(2026, 7, 25))
    assert calls == [("morning", date(2026, 7, 25))]


def test_closing_candidates_dedupe_by_code(db: Session):
    """尾盘同 code 多策略：保留最高 base score 一条候选。"""
    from desk_ai.refine import ResearchRefineService

    asof = date(2026, 7, 24)
    db.add(
        ClosingPick(
            asof=asof,
            strategy_id="s1",
            pick_type="stock",
            code="600519.SH",
            name="茅台",
            score=1.0,
            meta_json="{}",
        )
    )
    db.add(
        ClosingPick(
            asof=asof,
            strategy_id="s2",
            pick_type="stock",
            code="600519.SH",
            name="茅台",
            score=3.0,
            meta_json="{}",
        )
    )
    db.commit()

    seen: list[dict] = []

    def scorer(symbol: str, name: str, context: dict):
        seen.append(context)
        return _price_plan(symbol, score=90, confidence=90, rationale="ok")

    report = ResearchRefineService(db, scorer=scorer).run("closing", asof, top_n=5, min_confidence=70)
    assert report.candidates_evaluated == 1
    assert len(seen) == 1
    assert seen[0].get("base_score") == 3.0
    assert len(report.picks) == 1


def test_maybe_feishu_prefers_image_falls_back_to_text(db: Session, monkeypatch: pytest.MonkeyPatch):
    """
    飞书优先发表格图：sent 不发文本；no_credentials 回落 send。

    @param db: 内存库 Session
    @param monkeypatch: pytest monkeypatch
    """
    from unittest.mock import MagicMock, patch

    from desk_common.contracts import ResearchPickItem
    from desk_ai.refine import ResearchRefineService

    asof = date(2026, 7, 24)
    picks = [
        ResearchPickItem(
            symbol="600519.SH",
            name="茅台",
            score=90.0,
            confidence=88.0,
            rationale="强势",
            rank=1,
            buy_low=1600.0,
            buy_high=1650.0,
            target_low=1700.0,
            target_high=1800.0,
            stop_loss=1550.0,
        )
    ]
    svc = ResearchRefineService(db)
    png = b"\x89PNG\r\n\x1a\n"

    with (
        patch("desk_alert.FeishuWebhookChannel") as ch_cls,
        patch(
            "desk_ai.research_table_image.render_research_table_png",
            return_value=png,
        ) as render_mock,
    ):
        ch = MagicMock()
        ch_cls.return_value = ch

        ch.send_image.return_value = {"status": "sent", "id": 1}
        svc._maybe_feishu(asof, "morning", picks)
        render_mock.assert_called_once()
        ch.send_image.assert_called_once()
        ch.send.assert_not_called()

        ch.reset_mock()
        render_mock.reset_mock()
        ch.send_image.return_value = {"status": "no_credentials", "id": 2}
        svc._maybe_feishu(asof, "morning", picks)
        render_mock.assert_called_once()
        ch.send_image.assert_called_once()
        ch.send.assert_called_once()
        send_args = ch.send.call_args
        assert send_args.args[0] == "投研精选·morning"
        assert send_args.kwargs.get("category") == "research"
        assert send_args.kwargs.get("dedupe_key") == f"research:morning:{asof}"
