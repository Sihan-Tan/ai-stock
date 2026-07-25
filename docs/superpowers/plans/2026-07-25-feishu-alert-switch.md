# 飞书告警开关 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为飞书告警增加总开关与按类别开关；关闭后自动告警不发 Webhook，测试推送仍可发。

**Architecture:** 配置写入 `.env`（`FEISHU_ALERT_ENABLED` / `FEISHU_ALERT_CATEGORIES`），经现有 Settings 管道读写。唯一拦截点在 `FeishuWebhookChannel.send`：非测试且（总开关关或托管类别未勾选）时落库 `disabled` 并跳过 POST。设置页飞书 Tab 提供 UI。

**Tech Stack:** pydantic-settings、SQLAlchemy、FastAPI、React + HeroUI、pytest

**Spec:** `docs/superpowers/specs/2026-07-25-feishu-alert-switch-design.md`

---

## File structure

| 文件 | 职责 |
|------|------|
| `packages/common/desk_common/settings.py` | 新增两个 Settings 字段与默认值 |
| `packages/common/desk_common/settings_store.py` | EDITABLE_ENV / public_settings / bool 解析 |
| `packages/alert/desk_alert/__init__.py` | `send(..., force=False)` 开关拦截 + 类别解析 |
| `apps/api/app/routes/settings.py` | SettingsPatch 透出新字段 |
| `apps/api/app/routes/alerts.py` | `AlertIn.force` 传给 send |
| `apps/web/src/pages/Settings.tsx` | 飞书 Tab：总开关 + 四类勾选 |
| `.env.example` | 文档化新变量 |
| `tests/test_feishu_alert.py` | 开关 / 类别 / force 单测 |

托管类别常量（UI 与拦截共用语义）：`morning` / `closing` / `paper` / `risk`。  
测试绕过：`force=True` 或 `category ∈ {test, manual}`。

---

### Task 1: Settings 字段 + store 映射

**Files:**
- Modify: `packages/common/desk_common/settings.py`
- Modify: `packages/common/desk_common/settings_store.py`
- Modify: `.env.example`
- Modify: `apps/api/app/routes/settings.py`

- [ ] **Step 1: 在 Settings 增加字段**

在 `feishu_sign_secret` 后插入：

```python
    feishu_webhook_url: str = ""
    feishu_sign_secret: str = ""
    """飞书告警总开关；False 时自动告警不发 Webhook。"""
    feishu_alert_enabled: bool = True
    """允许推送的类别（逗号分隔）；默认不含 risk。"""
    feishu_alert_categories: str = "morning,closing,paper"
```

- [ ] **Step 2: 更新 settings_store**

`EDITABLE_ENV` 增加：

```python
    "feishu_webhook_url": "FEISHU_WEBHOOK_URL",
    "feishu_sign_secret": "FEISHU_SIGN_SECRET",
    "feishu_alert_enabled": "FEISHU_ALERT_ENABLED",
    "feishu_alert_categories": "FEISHU_ALERT_CATEGORIES",
```

`public_settings()` 在飞书段增加：

```python
        "feishu_webhook_url": s.feishu_webhook_url,
        "feishu_sign_secret": _mask_secret(s.feishu_sign_secret),
        "feishu_sign_secret_set": bool(s.feishu_sign_secret),
        "feishu_alert_enabled": s.feishu_alert_enabled,
        "feishu_alert_categories": s.feishu_alert_categories,
```

在 `apply_settings_patch` 的 bool 字段元组中加入 `"feishu_alert_enabled"`（与 `risk_armed` 同组）。  
`feishu_alert_categories` 走现有 `else: str(raw).strip()` 分支即可。

- [ ] **Step 3: SettingsPatch + .env.example**

`SettingsPatch` 增加：

```python
    feishu_webhook_url: str | None = None
    feishu_sign_secret: str | None = None
    feishu_alert_enabled: bool | None = None
    feishu_alert_categories: str | None = None
```

`.env.example` 在飞书段增加：

```
# Feishu alert webhook
FEISHU_WEBHOOK_URL=
FEISHU_SIGN_SECRET=
# 总开关；false=自动告警静音（测试推送仍可发）
FEISHU_ALERT_ENABLED=true
# 允许的自动告警类别（逗号分隔）；默认不含 risk
FEISHU_ALERT_CATEGORIES=morning,closing,paper
```

- [ ] **Step 4: 冒烟读默认值**

Run:

```bash
python -c "from desk_common.settings import Settings; s=Settings(); print(s.feishu_alert_enabled, s.feishu_alert_categories)"
```

Expected: `True morning,closing,paper`

- [ ] **Step 5: Commit**（仅当用户要求提交时执行）

```bash
git add packages/common/desk_common/settings.py packages/common/desk_common/settings_store.py apps/api/app/routes/settings.py .env.example
git commit -m "$(cat <<'EOF'
feat(settings): add Feishu alert enable and category flags

EOF
)"
```

---

### Task 2: 通道拦截 + 单测（TDD）

**Files:**
- Modify: `packages/alert/desk_alert/__init__.py`
- Modify: `tests/test_feishu_alert.py`
- Modify: `apps/api/app/routes/alerts.py`

- [ ] **Step 1: 写失败单测**

在 `tests/test_feishu_alert.py` 追加（需 DB fixture；复用项目内存库模式，参考 `tests/test_auction_ingest.py` 的 `_db` 或 `conftest`）：

```python
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


# --- 保留原有 _interpret / sign 测试 ---


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
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_feishu_alert.py::test_send_disabled_when_master_off -v`

Expected: FAIL（`force` / `_category_allowed` 尚未实现，或行为仍为 sent）

- [ ] **Step 3: 实现通道拦截**

在 `packages/alert/desk_alert/__init__.py` 增加：

```python
MANAGED_ALERT_CATEGORIES = frozenset({"morning", "closing", "paper", "risk"})
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
```

改写 `send` 签名与逻辑：

```python
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

        payload = {"msg_type": "text", "content": {"text": f"{title}\n{body}"}}
        url = (self.settings.feishu_webhook_url or "").strip()
        if url:
            status = self._post_webhook(url, payload)
        else:
            status = "logged_only"
        return self._persist(title, body, cat, dedupe_key, status)

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
```

注意：`send` 内每次应 `self.settings = get_settings()` 或构造时读到的 settings 在单测里需 `get_settings.cache_clear()` 后重建 channel（测试已如此）。为保险，在 `send` 开头加一行 `self.settings = get_settings()`。

- [ ] **Step 4: API 透传 force**

`apps/api/app/routes/alerts.py`：

```python
class AlertIn(BaseModel):
    title: str
    body: str
    category: str = "signal"
    dedupe_key: str = ""
    force: bool = False


@router.post("/send")
def send_alert(body: AlertIn, db: Session = Depends(get_db)):
    return FeishuWebhookChannel(db).send(
        body.title,
        body.body,
        body.category,
        body.dedupe_key,
        force=body.force,
    )
```

设置页已用 `category: "test"`，可不改即可绕过；可选在测试请求里加 `"force": true` 双保险。

- [ ] **Step 5: 跑通单测**

Run: `pytest tests/test_feishu_alert.py -v`

Expected: 全部 PASS

- [ ] **Step 6: Commit**（仅当用户要求提交时执行）

```bash
git add packages/alert/desk_alert/__init__.py apps/api/app/routes/alerts.py tests/test_feishu_alert.py
git commit -m "$(cat <<'EOF'
feat(alert): gate Feishu sends by enable flag and categories

EOF
)"
```

---

### Task 3: 设置页 UI

**Files:**
- Modify: `apps/web/src/pages/Settings.tsx`

- [ ] **Step 1: 扩展类型与 EMPTY**

`AppSettings` 增加：

```typescript
  feishu_alert_enabled?: boolean;
  feishu_alert_categories?: string;
```

`EMPTY` 增加：

```typescript
  feishu_alert_enabled: true,
  feishu_alert_categories: "morning,closing,paper",
```

- [ ] **Step 2: 保存时带上字段**

在 `save` 的 `body` 中飞书段加入：

```typescript
        feishu_webhook_url: form.feishu_webhook_url,
        feishu_alert_enabled: Boolean(form.feishu_alert_enabled),
        feishu_alert_categories: form.feishu_alert_categories || "",
```

- [ ] **Step 3: 飞书 Tab 增加开关 UI**

在 Webhook / 签名 `grid` 之后、「测试推送」之前插入（风格对齐交易模式双开关）：

```tsx
                <div className="mt-4 space-y-3 rounded-lg border border-[var(--desk-line)] bg-[var(--desk-ink)] p-4">
                  <div className="text-sm font-medium text-[var(--desk-text)]">推送开关</div>
                  <p className="text-xs text-[var(--desk-mist)]">
                    关闭总开关后自动告警静音；测试推送仍可用。风控类默认关闭。
                  </p>
                  <label className="flex items-start gap-2 text-sm text-[var(--desk-text)]">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(form.feishu_alert_enabled)}
                      onChange={(e) => patch("feishu_alert_enabled", e.target.checked)}
                    />
                    <span>启用飞书告警（总开关）</span>
                  </label>
                  {(
                    [
                      { id: "morning", label: "早盘" },
                      { id: "closing", label: "尾盘" },
                      { id: "paper", label: "纸交易" },
                      { id: "risk", label: "风控" },
                    ] as const
                  ).map((item) => {
                    const set = new Set(
                      (form.feishu_alert_categories || "")
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean)
                    );
                    return (
                      <label
                        key={item.id}
                        className="flex items-start gap-2 text-sm text-[var(--desk-text)]"
                      >
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={set.has(item.id)}
                          onChange={(e) => {
                            if (e.target.checked) set.add(item.id);
                            else set.delete(item.id);
                            patch(
                              "feishu_alert_categories",
                              ["morning", "closing", "paper", "risk"]
                                .filter((k) => set.has(k))
                                .join(",")
                            );
                          }}
                        />
                        <span>{item.label}</span>
                      </label>
                    );
                  })}
                </div>
```

测试推送 body 可加 `"force": true`：

```typescript
          category: "test",
          force: true,
          dedupe_key: `settings-test-${Date.now()}`,
```

- [ ] **Step 4: 手动验收清单（实现者勾）**

1. 打开设置 → 飞书：看到总开关与四类  
2. 取消总开关 → 保存 → 跑早盘/尾盘，告警流出现 `disabled`  
3. 打开总开关、只关早盘 → 早盘 `disabled`、尾盘可发  
4. 总开关关时点「测试推送」仍成功（`sent` 或 `logged_only`）

- [ ] **Step 5: Commit**（仅当用户要求提交时执行）

```bash
git add apps/web/src/pages/Settings.tsx
git commit -m "$(cat <<'EOF'
feat(web): Feishu alert enable and category toggles in settings

EOF
)"
```

---

### Task 4: 规格状态 + 全量相关测试

**Files:**
- Modify: `docs/superpowers/specs/2026-07-25-feishu-alert-switch-design.md`（状态已改为「已确认」；实现完成后改为「已实现」）

- [x] **Step 1: 跑相关测试**

```bash
pytest tests/test_feishu_alert.py tests/test_core.py::test_morning_and_ai_skills -v --tb=line
```

若 `test_morning_and_ai_skills` 因 LLM 模型名无关失败可忽略，只要飞书断言路径不受影响。优先保证 `test_feishu_alert.py` 全绿。

- [x] **Step 2: 更新规格状态为「已实现」**

- [ ] **Step 3: Commit**（仅当用户要求提交时执行）

```bash
git add docs/superpowers/specs/2026-07-25-feishu-alert-switch-design.md docs/superpowers/plans/2026-07-25-feishu-alert-switch.md
git commit -m "$(cat <<'EOF'
docs: mark Feishu alert switch spec implemented

EOF
)"
```

---

## Spec coverage checklist

| Spec 项 | Task |
|---------|------|
| 总开关默认开 | 1 |
| 类别默认 morning,closing,paper（无 risk） | 1 |
| send 拦截 → disabled | 2 |
| force / test / manual 绕过 | 2 |
| 未知类别放行 | 2 `_category_allowed` |
| Settings API 透出 | 1 |
| 设置页 UI | 3 |
| .env.example | 1 |
| 验收单测 | 2、4 |

## Self-review

- 无 TBD /「类似 Task N」占位  
- `force` 签名与 API、前端一致  
- 托管类别集合与 UI 四项一致  
- Commit 步骤注明「仅当用户要求提交时执行」，避免违背仓库提交约定
