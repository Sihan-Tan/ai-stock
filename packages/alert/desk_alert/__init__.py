"""飞书告警。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_db.models import AlertRow


class FeishuWebhookChannel:
    """飞书自定义机器人。"""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def send(
        self, title: str, body: str, category: str = "signal", dedupe_key: str = ""
    ) -> dict[str, Any]:
        """
        发送告警；落库防抖（同 key 5 分钟内不重复发送）。

        @returns: 状态字典（status / id）
        """
        if dedupe_key:
            since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
            hit = self.db.scalar(
                select(AlertRow).where(
                    AlertRow.dedupe_key == dedupe_key, AlertRow.created_at >= since
                )
            )
            if hit:
                return {"status": "deduped", "id": hit.id}

        payload = {"msg_type": "text", "content": {"text": f"{title}\n{body}"}}
        url = (self.settings.feishu_webhook_url or "").strip()
        status = "skipped"
        if url:
            status = self._post_webhook(url, payload)
        else:
            status = "logged_only"

        row = AlertRow(
            channel="feishu",
            category=category,
            title=title[:128],
            body=body,
            dedupe_key=(dedupe_key or "")[:128],
            status=str(status)[:128],
        )
        self.db.add(row)
        self.db.flush()
        return {"status": status, "id": row.id}

    def _post_webhook(self, url: str, payload: dict[str, Any]) -> str:
        """
        POST 飞书 Webhook；校验 HTTP 与业务 code。

        @param url Webhook 地址
        @param payload 消息体
        @returns sent / failed:...
        """
        data: dict[str, Any] = dict(payload)
        if self.settings.feishu_sign_secret:
            ts = str(int(time.time()))
            # 飞书官方：key = "{timestamp}\n{secret}"，msg 为空，再 Base64
            string_to_sign = f"{ts}\n{self.settings.feishu_sign_secret}"
            sign = base64.b64encode(
                hmac.new(
                    string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).digest()
            ).decode("utf-8")
            data = {**payload, "timestamp": ts, "sign": sign}
        try:
            r = httpx.post(url, json=data, timeout=10.0)
        except Exception as exc:  # noqa: BLE001
            return f"failed:{exc}"
        if r.status_code >= 300:
            return f"failed:http_{r.status_code}"
        return _interpret_feishu_response(r.text)

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """告警流。"""
        rows = self.db.scalars(
            select(AlertRow).order_by(AlertRow.id.desc()).limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "category": r.category,
                "title": r.title,
                "body": r.body,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


def _interpret_feishu_response(text: str) -> str:
    """
    解析飞书响应：code==0 为成功；无 JSON/无 code 时视为 HTTP 已成功。

    @param text 响应正文
    """
    raw = (text or "").strip()
    if not raw:
        return "sent"
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return "sent"
    if not isinstance(obj, dict):
        return "sent"
    if "code" not in obj:
        return "sent"
    code = obj.get("code")
    try:
        code_i = int(code)
    except (TypeError, ValueError):
        return f"failed:bad_code:{code}"
    if code_i == 0:
        return "sent"
    msg = obj.get("msg") or obj.get("message") or ""
    return f"failed:code_{code_i}:{msg}"[:120]
