# 投研精选飞书图片表 + 持仓附名称 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 投研精选飞书改为 Pillow 表格 PNG 上传后发图；失败回退文本；持仓建议行在代码后附股票名称；设置页可配飞书 App 凭证。

**Architecture:** Settings 增加 `feishu_app_id`/`feishu_app_secret`；`FeishuWebhookChannel.send_image` 负责 token→上传→webhook image；`research_table_image.render_research_table_png` 画表；`refine._maybe_feishu` 优先发图；`append_advice_section` 批量解析名称。

**Tech Stack:** Python 3、Pillow、httpx、pytest、现有 Settings/Settings UI、飞书开放平台 + 自定义机器人 Webhook。

**Spec:** `docs/superpowers/specs/2026-08-07-research-feishu-table-image-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| Modify: `pyproject.toml` | 增加 `Pillow` 依赖 |
| Modify: `packages/common/desk_common/settings.py` | app_id / app_secret 字段 |
| Modify: `packages/common/desk_common/settings_store.py` | EDITABLE / SECRET / public_settings |
| Modify: `packages/alert/desk_alert/__init__.py` | `send_image` + 上传辅助 |
| Create: `tests/test_feishu_send_image.py` | mock 上传与发图 |
| Create: `packages/ai/desk_ai/research_table_image.py` | 表格 PNG |
| Create: `tests/test_research_table_image.py` | 画表单测 |
| Modify: `packages/ai/desk_ai/refine.py` | `_maybe_feishu` 优先图片 |
| Modify: `packages/positions_advice/desk_positions_advice/format.py` | 附名称 |
| Create/Modify: `packages/positions_advice/.../names.py` 或 format 内辅助 | 批量解析名称 |
| Modify: `tests/test_positions_advice.py` | 名称行断言 |
| Modify: `apps/web/src/pages/Settings.tsx` | App ID/Secret 表单项 |
| Modify: `docs/superpowers/specs/2026-08-07-research-feishu-table-image-design.md` | 状态→已实现 |

---

### Task 1: Settings 凭证字段

**Files:**
- Modify: `packages/common/desk_common/settings.py`
- Modify: `packages/common/desk_common/settings_store.py`

- [ ] **Step 1: Settings 增加字段**

在 `feishu_sign_secret` 附近：

```python
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
```

- [ ] **Step 2: settings_store**

`EDITABLE_ENV` 增加：

```python
    "feishu_app_id": "FEISHU_APP_ID",
    "feishu_app_secret": "FEISHU_APP_SECRET",
```

`SECRET_FIELDS` 增加 `"feishu_app_secret"`（app_id 可明文展示）。

`public_settings()` 增加：

```python
        "feishu_app_id": s.feishu_app_id,
        "feishu_app_secret": _mask_secret(s.feishu_app_secret),
        "feishu_app_secret_set": bool(s.feishu_app_secret),
```

确保 `apply_settings_patch` 对带 `*` 的 secret 不覆盖（现有 SECRET_FIELDS 逻辑已覆盖 `feishu_app_secret`）。

- [ ] **Step 3: Commit**

```powershell
git add packages/common/desk_common/settings.py packages/common/desk_common/settings_store.py
$msg = @"
feat(settings): 飞书 App ID/Secret 配置项
"@
git commit -m $msg
```

---

### Task 2: `send_image`（TDD）

**Files:**
- Modify: `packages/alert/desk_alert/__init__.py`
- Create: `tests/test_feishu_send_image.py`

- [ ] **Step 1: 写失败单测**

```python
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
```

（若项目 `test_feishu_alert.py` 的 fixture 可复用，优先复用其 `alert_db` 模式。）

- [ ] **Step 2: 跑测确认失败**

`pytest tests/test_feishu_send_image.py -v` → FAIL（无 `send_image`）

- [ ] **Step 3: 实现**

在 `desk_alert/__init__.py`：

```python
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

    @returns status: sent | deduped | disabled | no_credentials | failed:...
    """
    # 1) 去重、开关、类别：复用 send 的同一套判断；body 摘要 f"[image] {title}"
    # 2) app_id/secret 为空 → persist no_credentials / failed:no_credentials
    # 3) _feishu_tenant_token() → _feishu_upload_image(token, image_bytes) → image_key
    # 4) payload = {"msg_type":"image","content":{"image_key": image_key}}
    # 5) _post_webhook；persist
```

辅助（模块级或私有方法）：

```python
def _feishu_tenant_token(app_id: str, app_secret: str) -> str:
    r = httpx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10.0,
    )
    # code==0 → tenant_access_token；否则 raise/返回失败

def _feishu_upload_image(token: str, image_bytes: bytes) -> str:
    # POST https://open.feishu.cn/open-apis/im/v1/images
    # headers Authorization: Bearer {token}
    # files: image=(file.png, bytes, image/png); data image_type=message
    # → data.image_key
```

- [ ] **Step 4: 跑测通过并 Commit**

```powershell
pytest tests/test_feishu_send_image.py tests/test_feishu_alert.py -q
git add packages/alert/desk_alert/__init__.py tests/test_feishu_send_image.py
$msg = @"
feat(alert): 飞书图片上传与 send_image
"@
git commit -m $msg
```

---

### Task 3: 表格 PNG 渲染（TDD）

**Files:**
- Create: `packages/ai/desk_ai/research_table_image.py`
- Create: `tests/test_research_table_image.py`
- Modify: `pyproject.toml`（`dependencies` 增加 `"Pillow>=10.0.0"`）

- [ ] **Step 1: 依赖**

```toml
  "Pillow>=10.0.0",
```

- [ ] **Step 2: 单测**

```python
"""投研精选表格 PNG。"""

from __future__ import annotations

from datetime import date

from desk_common.contracts import ResearchPickItem
from desk_ai.research_table_image import render_research_table_png, wrap_rationale_lines


def test_wrap_rationale_max_three_lines():
    lines = wrap_rationale_lines("一" * 200, max_chars_per_line=12, max_lines=3)
    assert len(lines) <= 3
    assert lines[-1].endswith("…") or len("".join(lines)) <= 36


def test_render_png_header_and_bytes():
    picks = [
        ResearchPickItem(
            rank=1,
            symbol="600519.SH",
            name="贵州茅台",
            score=90,
            confidence=88,
            buy_low=1600,
            buy_high=1650,
            target_low=1700,
            target_high=1800,
            stop_loss=1550,
            rationale="强势" + "理由" * 40,
        )
    ]
    raw = render_research_table_png(date(2026, 8, 7), "morning", picks)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 500
```

（若 `ResearchPickItem` 字段名不同，以 `desk_common.contracts` 为准。）

- [ ] **Step 3: 实现 `research_table_image.py`**

要点：

- `wrap_rationale_lines(text, max_chars_per_line=14, max_lines=3) -> list[str]`
- `render_research_table_png(asof, source, picks, *, errors=None) -> bytes`
- 顶栏：`投研精选·{source}  {asof}  共 N 只`
- 列宽估算 + 行高随理由行数变化
- 字体：`msyh.ttc` / `msyh.ttf` / `SimHei` / Pillow 默认
- 颜色：深底 `#0f1419`、表头 `#1a2332`、文字 `#e8eef5`、线 `#2a3544`

- [ ] **Step 4: 跑测 Commit**

```powershell
pytest tests/test_research_table_image.py -v
git add pyproject.toml packages/ai/desk_ai/research_table_image.py tests/test_research_table_image.py
$msg = @"
feat(ai): 投研精选 Pillow 表格图
"@
git commit -m $msg
```

（若需 `pnpm`/`pip install Pillow` 使本地可跑，在 worktree 执行 `pip install Pillow`。）

---

### Task 4: `_maybe_feishu` 优先发图

**Files:**
- Modify: `packages/ai/desk_ai/refine.py`
- Modify: `tests/test_research_refine.py`（若有 feishu mock，补图片优先用例）

- [ ] **Step 1: 改 `_maybe_feishu`**

```python
    def _maybe_feishu(...):
        if not picks:
            return
        try:
            from desk_alert import FeishuWebhookChannel
            from desk_ai.research_table_image import render_research_table_png

            title = f"投研精选·{source}"
            dedupe = f"research:{source}:{asof}"
            ch = FeishuWebhookChannel(self.db)
            try:
                png = render_research_table_png(asof, source, picks, errors=errors)
                img_status = ch.send_image(
                    title, png, category="research", dedupe_key=dedupe
                )
                st = str(img_status.get("status") or "")
                if st == "sent" or st == "deduped" or st == "disabled":
                    return
            except Exception:  # noqa: BLE001
                logger.exception("research refine image send failed; fallback text")

            body = format_research_feishu_body(asof, source, picks, errors=errors)
            ch.send(title, body, category="research", dedupe_key=dedupe)
        except Exception:  # noqa: BLE001
            logger.exception("research refine feishu send failed")
```

注意：图片失败回退文本时，若图片路径已写入 dedupe 行，文本可能被 dedupe——实现上：

- **优先**：`send_image` 仅在真正 webhook 成功后才 persist dedupe；`no_credentials`/`failed` 不占成功 dedupe，或使用不同 persist 策略让回退 `send` 仍可发出。
- 推荐：`send_image` 在 `no_credentials`/上传失败时 **不写 dedupe 成功行**（可写 status 失败行但不设相同 dedupe 拦截，或失败不写 dedupe_key）。最简单：**失败不 persist dedupe_key**（空 key），成功才写 `dedupe_key`。

- [ ] **Step 2: 单测**（可选但推荐）mock `send_image` 返回 `no_credentials` 时断言调用了 `send`。

- [ ] **Step 3: Commit**

```powershell
$msg = @"
feat(ai): 投研精选飞书优先推表格图
"@
git commit -m $msg
```

---

### Task 5: 持仓建议附名称

**Files:**
- Modify: `packages/positions_advice/desk_positions_advice/format.py`
- Modify: `tests/test_positions_advice.py`

- [ ] **Step 1: 扩展 `append_advice_section`**

签名增加可选 `name_by_symbol: dict[str, str] | None = None`，或内部若传入 `db` 则解析。为保持纯函数易测，推荐：

```python
def append_advice_section(
    content: str,
    advice: dict[str, Any],
    *,
    name_by_symbol: dict[str, str] | None = None,
) -> str:
    ...
            sym = str(it.get("symbol") or "")
            name = ""
            if name_by_symbol:
                name = str(name_by_symbol.get(sym) or "").strip()
            if not name:
                name = str(it.get("name") or "").strip()
            action = ...
            reason = ...
            mid = f"{sym} {name}".strip() if name else sym
            lines.append(f"{mid} {action}｜{reason}".strip())
```

- [ ] **Step 2: 名称解析辅助**

同包新增 `resolve_symbol_names(db, symbols: list[str]) -> dict[str, str]`：

```python
# 1) quotes_snapshot 批量
# 2) 缺失的再 get_security_meta / SecurityMeta
```

在 `advise_advice` 返回前把 names 填进 items，**或**在 morning/closing 调用 `append_advice_section` 处传入 `name_by_symbol`。优先在 `advise_advice` 内 enrich items 的 `name` 字段，则 format 只需读 `it.name`，调用点少改。

推荐路径：

1. `advise_advice` 末尾对 items 补 `name`
2. `append_advice_section` 读 `it.get("name")`

- [ ] **Step 3: 测试**

```python
def test_append_advice_section_includes_name():
    base = "【竞价强势】"
    advice = {
        "source": "live",
        "items": [{"symbol": "600000.SH", "name": "浦发银行", "action": "持有", "reason": "稳"}],
    }
    out = append_advice_section(base, advice)
    assert "600000.SH 浦发银行 持有｜稳" in out


def test_append_advice_section_without_name():
    advice = {
        "source": "live",
        "items": [{"symbol": "600000.SH", "action": "持有", "reason": "稳"}],
    }
    out = append_advice_section("X", advice)
    assert "600000.SH 持有｜稳" in out
```

- [ ] **Step 4: Commit**

```powershell
$msg = @"
feat(positions-advice): 持仓建议行附股票名称
"@
git commit -m $msg
```

---

### Task 6: 设置页 UI

**Files:**
- Modify: `apps/web/src/pages/Settings.tsx`

- [ ] **Step 1:** Settings 类型与默认 form 增加 `feishu_app_id`、`feishu_app_secret`、`feishu_app_secret_set?`

- [ ] **Step 2:** 飞书区块在签名密钥下增加 App ID、App Secret 输入（Secret 与 `feishu_sign_secret` 相同：已配置脱敏、留空不改、保存时若含 `*` 则不提交覆盖）

- [ ] **Step 3:** Commit

```powershell
$msg = @"
feat(web): 设置页飞书 App 凭证
"@
git commit -m $msg
```

---

### Task 7: 规格状态与总验证

- [ ] 规格头改为 `已实现`
- [ ] 跑：

```powershell
pytest tests/test_feishu_send_image.py tests/test_feishu_alert.py tests/test_research_table_image.py tests/test_positions_advice.py tests/test_research_refine.py -q
```

- [ ] Commit：`docs: 投研精选图片表规格标为已实现`

---

## Self-Review

1. **Spec coverage:** 凭证/send_image/表格图/精选优先图/持仓名称/设置页/回退/测试均有 Task。
2. **Placeholder scan:** 无 TBD；Feishu URL 与字段已写明。
3. **Consistency:** `send_image` 失败不阻断文本回退；`dedupe` 行为在 Task 4 已约束。
