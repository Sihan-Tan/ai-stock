"""飞书 send_image：上传 + webhook image。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401
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


def test_send_image_no_credentials_returns_failed(alert_db, monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "")
    monkeypatch.setenv("FEISHU_APP_SECRET", "")
    get_settings.cache_clear()
    ch = FeishuWebhookChannel(alert_db)
    out = ch.send_image("投研精选·morning", b"\x89PNG", category="research", dedupe_key="t1")
    assert str(out["status"]).startswith("failed:") or out["status"] == "no_credentials"


def test_send_image_success(alert_db):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    ch = FeishuWebhookChannel(alert_db)

    class FakeResp:
        def __init__(self, payload, status_code=200):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    def fake_post(url, **kwargs):
        if "tenant_access_token" in url:
            return FakeResp({"code": 0, "tenant_access_token": "tok", "expire": 7200})
        if "im/v1/images" in url:
            return FakeResp({"code": 0, "data": {"image_key": "img_xxx"}})
        # webhook
        body = kwargs.get("json") or {}
        assert body.get("msg_type") == "image"
        assert body.get("content", {}).get("image_key") == "img_xxx"
        return FakeResp({"code": 0, "msg": "success"})

    with patch("desk_alert.httpx.post", side_effect=fake_post):
        out = ch.send_image("投研精选·morning", png, category="research", dedupe_key="img:ok")
    assert out["status"] == "sent"
