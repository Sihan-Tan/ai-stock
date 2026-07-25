"""LLM 复盘生成与跳过逻辑。"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

from desk_review import ReviewService, generate_review, maybe_auto_review
from desk_review.generate import _parse_review_payload
from desk_review.scheduler import build_review_scheduler


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    session = Session(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


def test_parse_review_payload():
    raw = json.dumps(
        {
            "content": "## 大盘\n上证下跌",
            "deviations": [{"type": "execution", "summary": "滑点偏高", "severity": "medium"}],
        },
        ensure_ascii=False,
    )
    parsed = _parse_review_payload(raw)
    assert parsed is not None
    assert "大盘" in parsed["content"]
    assert parsed["deviations"][0]["type"] == "execution"


def test_generate_review_skip_existing(db, monkeypatch):
    ReviewService(db).upsert(date(2026, 7, 25), "手写", [{"type": "note"}])
    db.commit()

    def boom(system: str, user: str) -> str:
        raise AssertionError("should not call llm")

    out = generate_review(db, date(2026, 7, 25), force=False, llm_call=boom)
    assert out["status"] == "skipped"


def test_generate_review_force_with_mock_llm(db, monkeypatch):
    monkeypatch.setattr(
        "desk_review.generate.prefetch_review_facts",
        lambda db, asof, strategy_id=None: {
            "asof": asof.isoformat(),
            "market": [{"symbol": "000001.SH", "name": "上证", "chg_pct": -0.5}],
            "sentiment": {"limit_up_count": 40},
            "execution": {"trades": 0},
            "attribution": {"status": "empty"},
        },
    )

    def fake_llm(system: str, user: str) -> str:
        return json.dumps(
            {
                "content": "## 大盘\n下跌\n## 小结\nok",
                "deviations": [{"type": "market", "summary": "弱势", "severity": "low"}],
            },
            ensure_ascii=False,
        )

    out = generate_review(db, date(2026, 7, 25), force=True, llm_call=fake_llm)
    assert out["status"] == "ok"
    assert "大盘" in out["content"]
    got = ReviewService(db).get(date(2026, 7, 25))
    assert got is not None
    assert any(d.get("type") == "llm" for d in got["deviations"])


def test_maybe_auto_review_respects_flag(db, monkeypatch):
    monkeypatch.setenv("REVIEW_AUTO", "false")
    get_settings.cache_clear()
    assert maybe_auto_review(db, date(2026, 7, 25)) is None


def test_build_review_scheduler_dry_run():
    sched, ids = build_review_scheduler(dry_run=True)
    assert "review_auto_close" in ids
    assert len(sched.get_jobs()) == 1
