"""desk_ai tools 白名单与 dispatch 测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401


@pytest.fixture()
def db_session():
    """内存库 Session，供 dispatch_tool 使用。"""
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    db = Session(get_engine())
    try:
        yield db
    finally:
        db.close()
        reset_engine()
        get_settings.cache_clear()


def test_dispatch_unknown_tool(db_session):
    """未知工具名应返回 error。"""
    from desk_ai.tools import dispatch_tool

    assert dispatch_tool(db_session, "place_order", {})["error"].startswith("unknown")


def test_dispatch_get_financials(db_session, monkeypatch):
    """get_financials 走 FinancialService。"""
    monkeypatch.setattr(
        "desk_market.financials.FinancialService.get_financials",
        lambda self, symbol, years=5: {"symbol": symbol, "source": "qmt", "metrics": []},
    )
    from desk_ai.tools import dispatch_tool

    out = dispatch_tool(db_session, "get_financials", {"symbol": "600519"})
    assert out["source"] == "qmt"


@pytest.mark.asyncio
async def test_session_tools_loop_one_round(db_session, monkeypatch):
    """mock LLM 一轮 tool_calls 后再返回正文。"""
    from desk_ai.session import NanobotResearchSession

    class Msg:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class Choice:
        def __init__(self, message):
            self.message = message

    class Resp:
        def __init__(self, message):
            self.choices = [Choice(message)]

    class FakeTC:
        def __init__(self, id, name, arguments):
            self.id = id
            self.type = "function"
            self.function = type("F", (), {"name": name, "arguments": arguments})()

    calls = {"n": 0}

    async def fake_create(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return Resp(Msg(tool_calls=[FakeTC("1", "get_financials", '{"symbol":"600519.SH"}')]))
        return Resp(Msg(content="ROE 来自工具结果，财务稳健。"))

    monkeypatch.setattr(
        "desk_market.financials.FinancialService.get_financials",
        lambda self, symbol, years=5: {
            "symbol": symbol,
            "source": "qmt",
            "metrics": [{"roe": 0.25}],
        },
    )

    session = NanobotResearchSession(db_session)
    monkeypatch.setattr(session, "_chat_create", fake_create)
    monkeypatch.setattr(session.settings, "llm_api_key", "test")

    chunks = []
    async for c in session.run(
        [{"role": "user", "content": "茅台财务怎么样"}],
        skill_hint="financial-analysis",
    ):
        chunks.append(c)
    text = "".join(chunks)
    assert "get_financials" in text or "ROE" in text
    assert calls["n"] >= 2


def test_skill_loader_includes_research_skills():
    """SkillLoader 应包含投研专项 skills。"""
    from desk_ai.skills import SkillLoader

    names = {s["name"] for s in SkillLoader().list()}
    assert "write-report" in names
    assert "financial-analysis" in names


@pytest.mark.asyncio
async def test_session_llm_auth_error_yields_message(db_session, monkeypatch):
    """LLM 401 时流式返回可读提示，而不是抛出异常掐断连接。"""
    from desk_ai.session import NanobotResearchSession

    class AuthError(Exception):
        """模拟 openai.AuthenticationError。"""

    AuthError.__name__ = "AuthenticationError"

    async def boom(**kwargs):
        raise AuthError("Error code: 401 - Authentication Fails")

    session = NanobotResearchSession(db_session)
    monkeypatch.setattr(session, "_chat_create", boom)
    monkeypatch.setattr(session.settings, "llm_api_key", "bad-key")

    chunks = []
    async for c in session.run([{"role": "user", "content": "测试"}]):
        chunks.append(c)
    text = "".join(chunks)
    assert "认证失败" in text or "API Key" in text
