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

MANAGED_ALERT_CATEGORIES = frozenset({"morning", "closing", "paper", "risk", "research"})
TEST_ALERT_CATEGORIES = frozenset({"test", "manual"})


def _parse_alert_categories(raw: str) -> set[str]:
    """解析逗号分隔类别为小写集合。"""
    return {c.strip().lower() for c in (raw or "").split(",") if c.strip()}


def _category_allowed(category: str, categories_csv: str) -> bool:
    """
    托管类别须在允许列表；未知类别在总开关开启时放行。

    @param category: 告警类别
    @param categories_csv: FEISHU_ALERT_CATEGORIES
    """
    cat = (category or "").strip().lower()
    allowed = _parse_alert_categories(categories_csv)
    if cat in MANAGED_ALERT_CATEGORIES:
        return cat in allowed
    return True


class FeishuWebhookChannel:
    """飞书自定义机器人。"""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def send(
        self,
        title: str,
        body: str,
        category: str = "signal",
        dedupe_key: str = "",
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        发送告警；落库防抖（同 key 5 分钟内不重复发送）。
        总开关/类别关闭时不 POST，status=disabled；force 或测试类别绕过。

        @returns: 状态字典（status / id）
        """
        self.settings = get_settings()
        if dedupe_key:
            since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
            hit = self.db.scalar(
                select(AlertRow).where(
                    AlertRow.dedupe_key == dedupe_key, AlertRow.created_at >= since
                )
            )
            if hit:
                return {"status": "deduped", "id": hit.id}

        cat = (category or "signal").strip().lower() or "signal"
        is_test = force or cat in TEST_ALERT_CATEGORIES
        if not is_test:
            if not self.settings.feishu_alert_enabled:
                return self._persist(title, body, cat, dedupe_key, "disabled")
            if not _category_allowed(cat, self.settings.feishu_alert_categories):
                return self._persist(title, body, cat, dedupe_key, "disabled")

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {"msg_type": "text", "content": {"text": f"{title}  {ts}\n{body}"}}
        url = (self.settings.feishu_webhook_url or "").strip()
        if url:
            status = self._post_webhook(url, payload)
        else:
            status = "logged_only"
        return self._persist(title, body, cat, dedupe_key, status)

    def send_image(
        self,
        title: str,
        image_bytes: bytes,
        category: str = "signal",
        dedupe_key: str = "",
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        上传 PNG 并以 image 消息发送；开关/类别/去重与 send 一致。

        @param title 告警标题
        @param image_bytes PNG 字节
        @param category 告警类别
        @param dedupe_key 去重键；失败时不落库同 key，便于文本回退
        @param force 强制发送（绕过开关）
        @returns status: sent | deduped | disabled | no_credentials | failed:...
        """
        self.settings = get_settings()
        body = f"[image] {title}"
        if dedupe_key:
            since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
            hit = self.db.scalar(
                select(AlertRow).where(
                    AlertRow.dedupe_key == dedupe_key, AlertRow.created_at >= since
                )
            )
            if hit:
                return {"status": "deduped", "id": hit.id}

        cat = (category or "signal").strip().lower() or "signal"
        is_test = force or cat in TEST_ALERT_CATEGORIES
        if not is_test:
            if not self.settings.feishu_alert_enabled:
                return self._persist(title, body, cat, dedupe_key, "disabled")
            if not _category_allowed(cat, self.settings.feishu_alert_categories):
                return self._persist(title, body, cat, dedupe_key, "disabled")

        app_id = (self.settings.feishu_app_id or "").strip()
        app_secret = (self.settings.feishu_app_secret or "").strip()
        if not app_id or not app_secret:
            return self._persist(title, body, cat, "", "no_credentials")

        try:
            token = _feishu_tenant_token(app_id, app_secret)
            image_key = _feishu_upload_image(token, image_bytes)
        except Exception as exc:  # noqa: BLE001
            return self._persist(title, body, cat, "", f"failed:{exc}"[:128])

        payload = {"msg_type": "image", "content": {"image_key": image_key}}
        url = (self.settings.feishu_webhook_url or "").strip()
        if url:
            status = self._post_webhook(url, payload)
        else:
            status = "logged_only"
        # 失败不占 dedupe，便于同 key 文本回退
        persist_key = dedupe_key if status in ("sent", "logged_only") else ""
        return self._persist(title, body, cat, persist_key, status)

    def _persist(
        self,
        title: str,
        body: str,
        category: str,
        dedupe_key: str,
        status: str,
    ) -> dict[str, Any]:
        """写入 alerts 行并返回 status/id。"""
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


def _feishu_tenant_token(app_id: str, app_secret: str) -> str:
    """
    获取飞书 tenant_access_token。

    @param app_id 应用 App ID
    @param app_secret 应用 App Secret
    @returns tenant_access_token
    """
    r = httpx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10.0,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"token_http_{r.status_code}")
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("token:bad_json")
    try:
        code_i = int(data.get("code", -1))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"token:bad_code:{data.get('code')}") from exc
    if code_i != 0:
        msg = data.get("msg") or data.get("message") or ""
        raise RuntimeError(f"token:code_{code_i}:{msg}")
    token = (data.get("tenant_access_token") or "").strip()
    if not token:
        raise RuntimeError("token:empty")
    return token


def _feishu_upload_image(token: str, image_bytes: bytes) -> str:
    """
    上传 PNG 到飞书，返回 image_key。

    @param token tenant_access_token
    @param image_bytes PNG 字节
    @returns image_key
    """
    r = httpx.post(
        "https://open.feishu.cn/open-apis/im/v1/images",
        headers={"Authorization": f"Bearer {token}"},
        data={"image_type": "message"},
        files={"image": ("file.png", image_bytes, "image/png")},
        timeout=30.0,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"upload_http_{r.status_code}")
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("upload:bad_json")
    try:
        code_i = int(data.get("code", -1))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"upload:bad_code:{data.get('code')}") from exc
    if code_i != 0:
        msg = data.get("msg") or data.get("message") or ""
        raise RuntimeError(f"upload:code_{code_i}:{msg}")
    image_key = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get(
        "image_key"
    ) or ""
    image_key = str(image_key).strip()
    if not image_key:
        raise RuntimeError("upload:empty_image_key")
    return image_key


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
