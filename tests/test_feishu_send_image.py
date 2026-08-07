"""飞书 send_image：上传 + webhook image。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
from desk_db.models import AlertRow
from desk_alert import FeishuWebhookChannel


@pytest.fixture()
def alert_db(monkeypatch):
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "sec_test")
    monkeypatch.setenv("FEISHU_ALERT_ENABLED", "1")
    monkeypatch.setenv("FEISHU_ALERT_CATEGORIES", "research,morning,closing")
    get_settings.cache_clear()
    session = Session(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


class _FakeResp:
    """httpx 响应替身。"""

    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_send_image_no_credentials_returns_failed(alert_db, monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "")
    monkeypatch.setenv("FEISHU_APP_SECRET", "")
    get_settings.cache_clear()
    ch = FeishuWebhookChannel(alert_db)
    out = ch.send_image("投研精选·morning", b"\x89PNG", category="research", dedupe_key="t1")
    assert out["status"] == "no_credentials"
    row = alert_db.get(AlertRow, out["id"])
    assert row is not None
    assert row.dedupe_key == ""


def test_send_image_success(alert_db):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    ch = FeishuWebhookChannel(alert_db)

    def fake_post(url, **kwargs):
        if "tenant_access_token" in url:
            return _FakeResp({"code": 0, "tenant_access_token": "tok", "expire": 7200})
        if "im/v1/images" in url:
            return _FakeResp({"code": 0, "data": {"image_key": "img_xxx"}})
        body = kwargs.get("json") or {}
        assert body.get("msg_type") == "image"
        assert body.get("content", {}).get("image_key") == "img_xxx"
        return _FakeResp({"code": 0, "msg": "success"})

    with patch("desk_alert.httpx.post", side_effect=fake_post):
        out = ch.send_image("投研精选·morning", png, category="research", dedupe_key="img:ok")
    assert out["status"] == "sent"


def test_send_image_upload_failure_clears_dedupe_for_text_fallback(alert_db):
    """
    上传失败不落库同 dedupe_key，后续文本 send 不被 dedupe。

    @param alert_db 告警 DB fixture
    """
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    ch = FeishuWebhookChannel(alert_db)
    key = "img:fail-fallback"

    def fake_post(url, **kwargs):
        if "tenant_access_token" in url:
            return _FakeResp({"code": 0, "tenant_access_token": "tok", "expire": 7200})
        if "im/v1/images" in url:
            return _FakeResp({"code": 1, "msg": "upload boom"})
        return _FakeResp({"code": 0, "msg": "success"})

    with patch("desk_alert.httpx.post", side_effect=fake_post):
        img_out = ch.send_image("投研精选·morning", png, category="research", dedupe_key=key)
    assert str(img_out["status"]).startswith("failed:")
    row = alert_db.get(AlertRow, img_out["id"])
    assert row is not None
    assert row.dedupe_key == ""

    ch._post_webhook = MagicMock(return_value="sent")  # type: ignore[method-assign]
    text_out = ch.send("投研精选·morning", "fallback body", category="research", dedupe_key=key)
    assert text_out["status"] == "sent"
    ch._post_webhook.assert_called_once()


def test_send_image_disabled_when_master_off(alert_db, monkeypatch):
    monkeypatch.setenv("FEISHU_ALERT_ENABLED", "false")
    get_settings.cache_clear()
    ch = FeishuWebhookChannel(alert_db)
    with patch("desk_alert.httpx.post") as post:
        out = ch.send_image("t", b"\x89PNG", category="research", dedupe_key="img:off")
    assert out["status"] == "disabled"
    post.assert_not_called()
