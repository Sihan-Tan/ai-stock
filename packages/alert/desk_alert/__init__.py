"""飞书告警。"""

from __future__ import annotations

import hashlib
import hmac
import base64
import time
from datetime import datetime, timedelta
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

    def send(self, title: str, body: str, category: str = "signal", dedupe_key: str = "") -> dict[str, Any]:
        """
        发送告警；落库防抖（同 key 5 分钟内不重复发送）。

        @returns: 状态字典
        """
        if dedupe_key:
            since = datetime.utcnow() - timedelta(minutes=5)
            hit = self.db.scalar(
                select(AlertRow).where(
                    AlertRow.dedupe_key == dedupe_key, AlertRow.created_at >= since
                )
            )
            if hit:
                return {"status": "deduped", "id": hit.id}

        payload = {"msg_type": "text", "content": {"text": f"{title}\n{body}"}}
        url = self.settings.feishu_webhook_url
        status = "skipped"
        if url:
            headers = {}
            data = payload
            if self.settings.feishu_sign_secret:
                ts = str(int(time.time()))
                string_to_sign = f"{ts}\n{self.settings.feishu_sign_secret}"
                sign = base64.b64encode(
                    hmac.new(
                        self.settings.feishu_sign_secret.encode("utf-8"),
                        string_to_sign.encode("utf-8"),
                        digestmod=hashlib.sha256,
                    ).digest()
                ).decode("utf-8")
                data = {**payload, "timestamp": ts, "sign": sign}
            try:
                r = httpx.post(url, json=data, timeout=10.0)
                status = "sent" if r.status_code < 300 else "failed"
            except Exception as exc:  # noqa: BLE001
                status = f"failed:{exc}"
        else:
            status = "logged_only"

        row = AlertRow(
            channel="feishu",
            category=category,
            title=title,
            body=body,
            dedupe_key=dedupe_key or "",
            status=status,
        )
        self.db.add(row)
        self.db.flush()
        return {"status": status, "id": row.id}

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
