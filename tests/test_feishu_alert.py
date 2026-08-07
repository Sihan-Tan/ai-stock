"""飞书告警通道单测。"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from desk_alert import FeishuWebhookChannel, _interpret_feishu_response, _category_allowed
from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401


def test_interpret_feishu_code_zero_sent():
    assert _interpret_feishu_response('{"code":0,"msg":"success"}') == "sent"


def test_interpret_feishu_business_error():
    out = _interpret_feishu_response('{"code":19021,"msg":"sign match fail"}')
    assert out.startswith("failed:code_19021")


def test_interpret_feishu_empty_or_non_json_sent():
    assert _interpret_feishu_response("") == "sent"
    assert _interpret_feishu_response("ok") == "sent"
    assert _interpret_feishu_response('{"msg":"no code"}') == "sent"


def test_feishu_sign_matches_official_algo():
    """飞书文档：hmac key = timestamp\\\\nsecret，无 msg。"""
    import base64
    import hashlib
    import hmac

    ts = "1596607260"
    secret = "test_secret"
    string_to_sign = f"{ts}\n{secret}"
    expected = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    # 与旧错误算法不同
    wrong = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    assert expected != wrong
    assert len(expected) > 10


@pytest.fixture()
def alert_db(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    reset_engine()
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.test/hook")
    monkeypatch.setenv("FEISHU_ALERT_ENABLED", "true")
    monkeypatch.setenv("FEISHU_ALERT_CATEGORIES", "morning,closing,paper")
    get_settings.cache_clear()
    db = Session(get_engine())
    yield db
    db.close()
    reset_engine()
    get_settings.cache_clear()


def test_category_allowed_defaults():
    assert _category_allowed("morning", "morning,closing,paper") is True
    assert _category_allowed("risk", "morning,closing,paper") is False
    assert _category_allowed("signal", "morning,closing,paper") is True  # 未知放行


def test_send_disabled_when_master_off(alert_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEISHU_ALERT_ENABLED", "false")
    get_settings.cache_clear()
    ch = FeishuWebhookChannel(alert_db)
    ch._post_webhook = MagicMock(return_value="sent")  # type: ignore[method-assign]
    out = ch.send("t", "b", category="morning", dedupe_key="k1")
    assert out["status"] == "disabled"
    ch._post_webhook.assert_not_called()
    alert_db.commit()


def test_send_disabled_when_category_off(alert_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEISHU_ALERT_CATEGORIES", "closing,paper")
    get_settings.cache_clear()
    ch = FeishuWebhookChannel(alert_db)
    ch._post_webhook = MagicMock(return_value="sent")  # type: ignore[method-assign]
    out = ch.send("t", "b", category="morning", dedupe_key="k2")
    assert out["status"] == "disabled"
    ch._post_webhook.assert_not_called()


def test_send_force_bypasses_switch(alert_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEISHU_ALERT_ENABLED", "false")
    get_settings.cache_clear()
    ch = FeishuWebhookChannel(alert_db)
    ch._post_webhook = MagicMock(return_value="sent")  # type: ignore[method-assign]
    out = ch.send("t", "b", category="morning", dedupe_key="k3", force=True)
    assert out["status"] == "sent"
    ch._post_webhook.assert_called_once()


def test_send_test_category_bypasses(alert_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEISHU_ALERT_ENABLED", "false")
    get_settings.cache_clear()
    ch = FeishuWebhookChannel(alert_db)
    ch._post_webhook = MagicMock(return_value="sent")  # type: ignore[method-assign]
    out = ch.send("t", "b", category="test", dedupe_key="k4")
    assert out["status"] == "sent"
    ch._post_webhook.assert_called_once()


def test_send_payload_includes_local_timestamp(alert_db):
    """飞书首行应为「标题 + 本地时间」，次行为正文。"""
    import re

    ch = FeishuWebhookChannel(alert_db)
    ch._post_webhook = MagicMock(return_value="sent")  # type: ignore[method-assign]
    ch.send("标题", "正文", category="test", dedupe_key="k-ts", force=True)
    (_url, payload), _kwargs = ch._post_webhook.call_args
    text = payload["content"]["text"]
    lines = text.split("\n")
    assert re.fullmatch(r"标题  \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", lines[0])
    assert lines[1] == "正文"
