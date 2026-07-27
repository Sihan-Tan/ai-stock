# 早盘/尾盘持仓建议 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在尾盘选股与早盘竞价强势选拔完成后，对当前持仓生成操作建议（含理由），与选股摘要合并为同一条飞书推送。

**Architecture:** 新建共享包 `desk_positions_advice`（读仓 → 可选规则候选 → 一次 LLM → 拼正文）。挂到 `ClosingPickService.run` 与 `MorningBriefService.run_post_auction` 选股落库之后、飞书发送之前。设置项控制开关 / 模式（`llm`|`hybrid`）/ 持仓源（`live`|`paper`）。

**Tech Stack:** Python 3.11、SQLAlchemy Session、现有 `BrokerService` / OpenAI 兼容 LLM、飞书 `FeishuWebhookChannel`、FastAPI settings 持久化、pytest、React Settings 页。

**Spec:** `docs/superpowers/specs/2026-07-27-positions-advice-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `packages/positions_advice/desk_positions_advice/__init__.py` | 导出 `advise_advice`、`append_advice_section`、动作常量 |
| `packages/positions_advice/desk_positions_advice/positions.py` | 读 live/paper 持仓、截断前 20 |
| `packages/positions_advice/desk_positions_advice/rules.py` | hybrid 规则候选 |
| `packages/positions_advice/desk_positions_advice/llm.py` | 解析 JSON、调 LLM、校验 action |
| `packages/positions_advice/desk_positions_advice/format.py` | 拼「持仓建议」段 |
| `packages/positions_advice/desk_positions_advice/service.py` | `advise_advice` 编排 |
| `packages/common/desk_common/settings.py` | 三字段 |
| `packages/common/desk_common/settings_store.py` | EDITABLE / public / update 校验 |
| `apps/web/src/pages/Settings.tsx` | UI 三控件 |
| `.env.example` | 注释示例 |
| `pyproject.toml` | package + pythonpath |
| `packages/closing_pick/desk_closing_pick/__init__.py` | 挂接建议 |
| `packages/morning_brief/desk_morning_brief/__init__.py` | 挂接建议 |
| `tests/test_positions_advice.py` | 单元 + 编排 |
| `tests/test_closing_pick.py` / `tests/test_morning_rest_day.py` | 挂点 mock（可增用例） |

---

### Task 1: Settings 三字段

**Files:**
- Modify: `packages/common/desk_common/settings.py`
- Modify: `packages/common/desk_common/settings_store.py`
- Modify: `.env.example`
- Modify: `pyproject.toml`（本 Task 也可延后到 Task 2 一并加 package；此处先只改 settings）

- [ ] **Step 1: 在 Settings 类增加字段**

在 `review_auto: bool = False` 后加入：

```python
    """早盘/尾盘选股后是否附带持仓建议。"""
    positions_advice_enabled: bool = True
    """持仓建议模式：llm=纯 LLM；hybrid=规则候选+LLM。"""
    positions_advice_mode: Literal["llm", "hybrid"] = "llm"
    """持仓源：live 或 paper。"""
    positions_advice_source: Literal["live", "paper"] = "live"
```

确保文件顶部已有 `from typing import Literal`。

- [ ] **Step 2: 更新 settings_store**

在 `EDITABLE_ENV` 增加：

```python
    "positions_advice_enabled": "POSITIONS_ADVICE_ENABLED",
    "positions_advice_mode": "POSITIONS_ADVICE_MODE",
    "positions_advice_source": "POSITIONS_ADVICE_SOURCE",
```

在 `public_settings()` 返回字典中增加：

```python
        "positions_advice_enabled": s.positions_advice_enabled,
        "positions_advice_mode": s.positions_advice_mode,
        "positions_advice_source": s.positions_advice_source,
```

在 bool 字段元组（含 `review_auto` 的那组）加入 `"positions_advice_enabled"`。

在校验区增加（`knowledge_retrieval` 校验附近）：

```python
    if "positions_advice_mode" in cleaned and cleaned["positions_advice_mode"] not in (
        "llm",
        "hybrid",
    ):
        raise ValueError("positions_advice_mode 须为 llm 或 hybrid")
    if "positions_advice_source" in cleaned and cleaned["positions_advice_source"] not in (
        "live",
        "paper",
    ):
        raise ValueError("positions_advice_source 须为 live 或 paper")
```

对 `positions_advice_mode` / `positions_advice_source` 走 `cleaned[field] = str(raw).strip().lower()`：把它们加入与 `trade_mode` 同类的 `elif field in (...)` 分支，或单独处理。

- [ ] **Step 3: 更新 .env.example**

在 `# REVIEW_AUTO=false` 附近增加：

```env
# POSITIONS_ADVICE_ENABLED=true
# POSITIONS_ADVICE_MODE=llm
# POSITIONS_ADVICE_SOURCE=live
```

- [ ] **Step 4: Commit**

```bash
git add packages/common/desk_common/settings.py packages/common/desk_common/settings_store.py .env.example
git commit -m "feat: 持仓建议设置项（开关/模式/持仓源）"
```

---

### Task 2: 包骨架 + format + 动作常量（TDD）

**Files:**
- Create: `packages/positions_advice/desk_positions_advice/__init__.py`
- Create: `packages/positions_advice/desk_positions_advice/format.py`
- Create: `tests/test_positions_advice.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 写失败测试（format + action 回退辅助可后置）**

创建 `tests/test_positions_advice.py`：

```python
"""持仓建议：格式化、解析、编排。"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MARKET_SCHEDULER_ENABLED", "0")

from desk_common.settings import get_settings
from desk_db import Base, get_engine, reset_engine
import desk_db.models  # noqa: F401

from desk_positions_advice.format import append_advice_section
from desk_positions_advice.llm import normalize_action, parse_advice_payload


@pytest.fixture()
def db():
    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())
    session = Session(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


def test_append_advice_section_empty_positions():
    base = "【尾盘选股】2026-07-27\n命中 1 只"
    advice = {
        "status": "empty",
        "source": "live",
        "section": "当前无持仓，跳过建议",
        "items": [],
    }
    out = append_advice_section(base, advice)
    assert "持仓建议（live）" in out
    assert "当前无持仓，跳过建议" in out
    assert out.startswith(base)


def test_normalize_action_closing_invalid():
    assert normalize_action("加仓", "closing") == ("持有", True)
    assert normalize_action("卖出", "closing") == ("卖出", False)


def test_normalize_action_morning():
    assert normalize_action("高抛低吸", "morning") == ("高抛低吸", False)
    assert normalize_action("低吸", "morning") == ("低吸", False)
    assert normalize_action("观望", "morning") == ("持有", True)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_positions_advice.py::test_append_advice_section_empty_positions -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 注册包路径**

`pyproject.toml` 的 `where = [...]` 与 `pythonpath = [...]` 都加入 `"packages/positions_advice"`。

- [ ] **Step 4: 实现 format + 常量 + normalize/parse 最小实现**

`format.py`：

```python
"""持仓建议推送文案。"""

from __future__ import annotations

from typing import Any


def append_advice_section(content: str, advice: dict[str, Any]) -> str:
    """
    将持仓建议段拼到选股正文后。

    @param content: 选股摘要
    @param advice: advise_advice 返回值（含 source / section 或 items）
    """
    source = str(advice.get("source") or "live")
    header = f"—— 持仓建议（{source}）——"
    section = str(advice.get("section") or "").strip()
    if not section:
        lines: list[str] = []
        note = str(advice.get("market_note") or "").strip()
        if note:
            lines.append(note)
        for it in advice.get("items") or []:
            if not isinstance(it, dict):
                continue
            sym = it.get("symbol") or ""
            action = it.get("action") or ""
            reason = it.get("reason") or ""
            lines.append(f"{sym} {action}｜{reason}")
        if advice.get("truncated"):
            lines.append("（持仓已截断，仅展示前 20 只）")
        section = "\n".join(lines) if lines else "（无建议条目）"
    return f"{content.rstrip()}\n\n{header}\n{section}"
```

`llm.py`（本 Task 先放 normalize + parse；generate 在 Task 5）：

```python
"""持仓建议 LLM：解析与动作校验。"""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")

CLOSING_ACTIONS = frozenset({"持有", "卖出"})
MORNING_ACTIONS = frozenset({"持有", "卖出", "高抛低吸", "低吸"})


def allowed_actions(session_kind: str) -> frozenset[str]:
    """按场景返回合法动作集合。"""
    if session_kind == "morning":
        return MORNING_ACTIONS
    return CLOSING_ACTIONS


def normalize_action(action: str, session_kind: str) -> tuple[str, bool]:
    """
    校验动作；非法则回退持有。

    @returns: (最终动作, 是否发生回退)
    """
    act = str(action or "").strip()
    if act in allowed_actions(session_kind):
        return act, False
    return "持有", True


def parse_advice_payload(text: str, session_kind: str) -> dict[str, Any] | None:
    """从模型输出解析 items + market_note；非法 action 回退持有。"""
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    items_in = obj.get("items")
    if not isinstance(items_in, list):
        return None
    items: list[dict[str, Any]] = []
    for it in items_in:
        if not isinstance(it, dict) or not it.get("symbol"):
            continue
        action, reverted = normalize_action(str(it.get("action") or ""), session_kind)
        reason = str(it.get("reason") or "").strip() or "（无理由）"
        if reverted:
            reason = f"{reason}（动作非法已回退持有）"
        items.append(
            {
                "symbol": str(it["symbol"]),
                "action": action,
                "reason": reason,
            }
        )
    return {
        "items": items,
        "market_note": str(obj.get("market_note") or "").strip() or None,
    }
```

`__init__.py`：

```python
"""早盘/尾盘持仓建议。"""

from desk_positions_advice.format import append_advice_section
from desk_positions_advice.llm import CLOSING_ACTIONS, MORNING_ACTIONS, normalize_action

__all__ = [
    "append_advice_section",
    "normalize_action",
    "CLOSING_ACTIONS",
    "MORNING_ACTIONS",
]
```

（`advise_advice` 在 Task 6 再导出。）

- [ ] **Step 5: 跑测试通过**

Run: `python -m pytest tests/test_positions_advice.py -v`  
Expected: 本 Task 相关 3 个 PASS（若尚无其他测试文件用例）

- [ ] **Step 6: Commit**

```bash
git add packages/positions_advice pyproject.toml tests/test_positions_advice.py
git commit -m "feat: positions_advice 格式化与动作枚举"
```

---

### Task 3: 读仓与截断

**Files:**
- Create: `packages/positions_advice/desk_positions_advice/positions.py`
- Modify: `tests/test_positions_advice.py`

- [ ] **Step 1: 写失败测试**

追加：

```python
from desk_db.models import PaperAccount, PaperPosition
from desk_positions_advice.positions import load_positions, truncate_positions


def test_truncate_positions_by_market_value():
    rows = [
        {"symbol": f"s{i}", "qty": 100, "cost": 10, "market_value": float(i), "pnl": 0}
        for i in range(25)
    ]
    out, truncated = truncate_positions(rows, limit=20)
    assert truncated is True
    assert len(out) == 20
    assert out[0]["symbol"] == "s24"


def test_load_paper_positions(db: Session):
    acc = PaperAccount(name="default", cash=1_000_000, equity=1_000_000)
    db.add(acc)
    db.flush()
    db.add(PaperPosition(account_id=acc.id, symbol="600000.SH", qty=100, cost=10.0))
    db.commit()
    loaded = load_positions(db, "paper")
    assert loaded["ok"] is True
    assert loaded["source"] == "paper"
    assert any(p["symbol"] == "600000.SH" for p in loaded["positions"])
```

确认 `PaperAccount` / `PaperPosition` 字段名与 `desk_db.models` 一致；若构造参数不同，按模型调整。

- [ ] **Step 2: 跑测确认失败**

Run: `python -m pytest tests/test_positions_advice.py::test_truncate_positions_by_market_value -v`  
Expected: FAIL import

- [ ] **Step 3: 实现 positions.py**

```python
"""持仓读取与截断。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

MAX_POSITIONS = 20


def truncate_positions(
    positions: list[dict[str, Any]], *, limit: int = MAX_POSITIONS
) -> tuple[list[dict[str, Any]], bool]:
    """
    按市值降序截断；无市值则按 |浮盈|。

    @returns: (截断后列表, 是否截断)
    """
    if len(positions) <= limit:
        return list(positions), False

    def sort_key(p: dict[str, Any]) -> float:
        mv = p.get("market_value")
        if mv is not None:
            try:
                return float(mv)
            except (TypeError, ValueError):
                pass
        try:
            return abs(float(p.get("pnl") or 0))
        except (TypeError, ValueError):
            return 0.0

    ranked = sorted(positions, key=sort_key, reverse=True)
    return ranked[:limit], True


def load_positions(db: Session, source: str) -> dict[str, Any]:
    """
    读取持仓。

    @param source: live | paper
    @returns: {ok, source, positions, error?, message?}
    """
    src = (source or "live").strip().lower()
    try:
        if src == "paper":
            from desk_broker import PaperBroker

            summary = PaperBroker(db).summary()
            positions = []
            for p in summary.get("positions") or []:
                if float(p.get("qty") or 0) <= 0:
                    continue
                qty = float(p["qty"])
                cost = float(p.get("cost") or 0)
                # paper summary 无现价时用成本近似市值
                last = float(p.get("last_price") or cost)
                mv = qty * last
                pnl = (last - cost) * qty
                positions.append(
                    {
                        "symbol": p["symbol"],
                        "qty": qty,
                        "cost": cost,
                        "last_price": last,
                        "market_value": mv,
                        "pnl": pnl,
                        "strategy_id": p.get("strategy_id"),
                    }
                )
            return {"ok": True, "source": "paper", "positions": positions, "message": None}
        # live
        from desk_broker import BrokerService

        snap = BrokerService(db).account_snapshot()
        positions = []
        for p in snap.get("positions") or []:
            if str(p.get("row_type") or "") == "sold":
                continue
            qty = float(p.get("qty") or 0)
            if qty <= 0:
                continue
            cost = float(p.get("cost") or 0)
            mv = p.get("market_value")
            if mv is None:
                last = float(p.get("last_price") or cost)
                mv = qty * last
            else:
                mv = float(mv)
                last = mv / qty if qty else cost
            pnl = (last - cost) * qty
            positions.append(
                {
                    "symbol": p["symbol"],
                    "qty": qty,
                    "cost": cost,
                    "last_price": last,
                    "market_value": mv,
                    "pnl": pnl,
                    "strategy_id": p.get("strategy_id"),
                }
            )
        return {
            "ok": True,
            "source": "live",
            "positions": positions,
            "message": snap.get("message"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "source": src,
            "positions": [],
            "error": str(exc),
            "message": str(exc),
        }
```

若 `PaperBroker` / `BrokerService` 导入路径不同，以 `packages/broker/desk_broker/__init__.py` 实际导出为准（常见为 `from desk_broker import BrokerService` 与 paper 的 `summary` 在同一服务类上——实现时核对：若只有 `BrokerService.summary()` 为 paper，则 paper 分支改用正确类）。

**核对要点：** 打开 `desk_broker/__init__.py`，确认 paper `summary` 与 live `account_snapshot` 的入口类名；按实调整 `load_positions`，不要臆造 API。

- [ ] **Step 4: 跑通测试**

Run: `python -m pytest tests/test_positions_advice.py::test_truncate_positions_by_market_value tests/test_positions_advice.py::test_load_paper_positions -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/positions_advice/desk_positions_advice/positions.py tests/test_positions_advice.py
git commit -m "feat: 持仓建议读仓与截断"
```

---

### Task 4: hybrid 规则候选

**Files:**
- Create: `packages/positions_advice/desk_positions_advice/rules.py`
- Modify: `tests/test_positions_advice.py`

- [ ] **Step 1: 写失败测试**

```python
from desk_positions_advice.rules import rule_candidates


def test_rule_candidates_closing_sell_on_big_drop():
    positions = [
        {
            "symbol": "600000.SH",
            "qty": 100,
            "cost": 10,
            "last_price": 8.5,
            "pnl": -150,
            "day_chg_pct": -0.06,
        }
    ]
    out = rule_candidates(positions, session_kind="closing")
    assert out[0]["symbol"] == "600000.SH"
    assert out[0]["action"] == "卖出"


def test_rule_candidates_exception_safe(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    # 若 rules 内部调用辅助失败，service 层会吞；此处保证单函数对坏数据不炸
    out = rule_candidates([{"symbol": "x"}], session_kind="morning")
    assert isinstance(out, list)
```

- [ ] **Step 2: 实现 rules.py**

```python
"""hybrid 模式：简单规则候选动作。"""

from __future__ import annotations

from typing import Any


def rule_candidates(
    positions: list[dict[str, Any]],
    *,
    session_kind: str,
) -> list[dict[str, Any]]:
    """
    为每只持仓给出规则候选（不强制最终动作）。

    尾盘：日跌幅 <= -5% 或浮亏相对成本 <= -8% → 卖出，否则持有。
    早盘：日涨 >= 5% → 高抛低吸；日跌 <= -3% → 低吸；浮亏严重 → 卖出；否则持有。
    """
    out: list[dict[str, Any]] = []
    for p in positions:
        try:
            sym = str(p.get("symbol") or "")
            if not sym:
                continue
            cost = float(p.get("cost") or 0) or 0.0
            last = float(p.get("last_price") or cost) or 0.0
            day = p.get("day_chg_pct")
            day_pct = float(day) if day is not None else None
            pnl_pct = ((last / cost) - 1.0) if cost > 0 else 0.0

            if session_kind == "morning":
                if pnl_pct <= -0.08 or (day_pct is not None and day_pct <= -0.05):
                    action, why = "卖出", "浮亏或竞价/日内跌幅偏大"
                elif day_pct is not None and day_pct >= 0.05:
                    action, why = "高抛低吸", "冲高可考虑高抛低吸"
                elif day_pct is not None and day_pct <= -0.03:
                    action, why = "低吸", "回调可考虑低吸"
                else:
                    action, why = "持有", "未见明确强弱信号"
            else:
                if (day_pct is not None and day_pct <= -0.05) or pnl_pct <= -0.08:
                    action, why = "卖出", "尾盘跌幅或浮亏偏大，不宜隔夜"
                else:
                    action, why = "持有", "跌幅可控，规则建议持有"

            out.append(
                {
                    "symbol": sym,
                    "action": action,
                    "rule_reason": why,
                }
            )
        except Exception:  # noqa: BLE001
            continue
    return out
```

- [ ] **Step 3: 跑测**

Run: `python -m pytest tests/test_positions_advice.py::test_rule_candidates_closing_sell_on_big_drop -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add packages/positions_advice/desk_positions_advice/rules.py tests/test_positions_advice.py
git commit -m "feat: 持仓建议 hybrid 规则候选"
```

---

### Task 5: LLM 生成

**Files:**
- Modify: `packages/positions_advice/desk_positions_advice/llm.py`
- Modify: `tests/test_positions_advice.py`

- [ ] **Step 1: 写失败测试**

```python
import json
from desk_positions_advice.llm import generate_advice_llm, parse_advice_payload


def test_parse_advice_payload_ok():
    raw = json.dumps(
        {
            "items": [{"symbol": "600000.SH", "action": "卖出", "reason": "走弱"}],
            "market_note": "情绪偏弱",
        },
        ensure_ascii=False,
    )
    parsed = parse_advice_payload(raw, "closing")
    assert parsed is not None
    assert parsed["items"][0]["action"] == "卖出"


def test_generate_advice_llm_mock():
    facts = {"positions": [{"symbol": "600000.SH"}], "session_kind": "closing"}

    def fake(system: str, user: str) -> str:
        return json.dumps(
            {
                "items": [
                    {"symbol": "600000.SH", "action": "持有", "reason": "ok"},
                ]
            },
            ensure_ascii=False,
        )

    out = generate_advice_llm(facts, session_kind="closing", llm_call=fake)
    assert out["status"] == "ok"
    assert out["items"][0]["symbol"] == "600000.SH"


def test_generate_advice_llm_error():
    def boom(system: str, user: str) -> str:
        raise RuntimeError("network")

    out = generate_advice_llm({}, session_kind="closing", llm_call=boom)
    assert out["status"] == "error"
```

- [ ] **Step 2: 实现 generate_advice_llm**

在 `llm.py` 追加（复用日终复盘的 OpenAI 调用风格）：

```python
import logging
from typing import Callable

from desk_common.settings import get_settings

logger = logging.getLogger(__name__)
LlmFn = Callable[[str, str], str]


def _default_llm_call(system: str, user: str) -> str:
    """同步调用 OpenAI 兼容 Chat。"""
    from openai import OpenAI
    from desk_ai.session import resolve_llm_model

    settings = get_settings()
    if not settings.llm_api_key:
        raise ValueError("未配置 LLM API Key")
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url or None)
    model = resolve_llm_model(settings.llm_provider, settings.llm_model)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return str(getattr(resp.choices[0].message, "content", None) or "")


def generate_advice_llm(
    facts: dict[str, Any],
    *,
    session_kind: str,
    llm_call: LlmFn | None = None,
) -> dict[str, Any]:
    """
    一次 LLM 生成持仓建议。

    @returns: {status, items?, market_note?, error?}
    """
    settings = get_settings()
    if llm_call is None and not settings.llm_api_key:
        return {"status": "error", "error": "未配置 LLM API Key", "items": []}

    actions = "、".join(sorted(allowed_actions(session_kind)))
    label = "早盘竞价后" if session_kind == "morning" else "尾盘选股后"
    system = (
        f"你是刻度 Desk {label}持仓建议助手。"
        "根据预取事实给出每只持仓的操作建议与简短理由，禁止编造未给出的数字。"
        "只输出一个 JSON 对象。"
    )
    user = (
        f"场景={session_kind}。合法 action 仅限：{actions}。\n"
        f"事实：\n{json.dumps(facts, ensure_ascii=False, default=str)}\n\n"
        '输出：{"items":[{"symbol":"...","action":"...","reason":"..."}],'
        '"market_note":"可选一句市场总评"}'
    )
    call = llm_call or _default_llm_call
    try:
        raw = call(system, user)
    except Exception as exc:  # noqa: BLE001
        logger.exception("positions advice llm failed")
        return {"status": "error", "error": str(exc), "items": []}

    parsed = parse_advice_payload(raw, session_kind)
    if not parsed:
        return {
            "status": "error",
            "error": "模型输出无法解析为 JSON",
            "items": [],
            "raw_preview": (raw or "")[:300],
        }
    return {
        "status": "ok",
        "items": parsed["items"],
        "market_note": parsed.get("market_note"),
    }
```

- [ ] **Step 3: 跑测**

Run: `python -m pytest tests/test_positions_advice.py -k "parse_advice or generate_advice" -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add packages/positions_advice/desk_positions_advice/llm.py tests/test_positions_advice.py
git commit -m "feat: 持仓建议 LLM 生成与解析"
```

---

### Task 6: `advise_advice` 编排

**Files:**
- Create: `packages/positions_advice/desk_positions_advice/service.py`
- Modify: `packages/positions_advice/desk_positions_advice/__init__.py`
- Modify: `tests/test_positions_advice.py`

- [ ] **Step 1: 写失败测试**

```python
from desk_positions_advice import advise_advice


def test_advise_advice_disabled(db, monkeypatch):
    monkeypatch.setattr(
        "desk_positions_advice.service.get_settings",
        lambda: type("S", (), {
            "positions_advice_enabled": False,
            "positions_advice_mode": "llm",
            "positions_advice_source": "live",
            "llm_api_key": "x",
        })(),
    )
    out = advise_advice(db, session_kind="closing", asof=date(2026, 7, 27))
    assert out["status"] == "disabled"


def test_advise_advice_empty_positions(db, monkeypatch):
    monkeypatch.setattr(
        "desk_positions_advice.service.get_settings",
        lambda: type("S", (), {
            "positions_advice_enabled": True,
            "positions_advice_mode": "llm",
            "positions_advice_source": "live",
            "llm_api_key": "x",
        })(),
    )
    monkeypatch.setattr(
        "desk_positions_advice.service.load_positions",
        lambda db, source: {"ok": True, "source": source, "positions": []},
    )
    out = advise_advice(db, session_kind="closing", asof=date(2026, 7, 27))
    assert out["status"] == "empty"
    assert "无持仓" in out["section"]


def test_advise_advice_llm_ok(db, monkeypatch):
    monkeypatch.setattr(
        "desk_positions_advice.service.get_settings",
        lambda: type("S", (), {
            "positions_advice_enabled": True,
            "positions_advice_mode": "llm",
            "positions_advice_source": "paper",
            "llm_api_key": "x",
        })(),
    )
    monkeypatch.setattr(
        "desk_positions_advice.service.load_positions",
        lambda db, source: {
            "ok": True,
            "source": "paper",
            "positions": [
                {
                    "symbol": "600000.SH",
                    "qty": 100,
                    "cost": 10,
                    "last_price": 11,
                    "market_value": 1100,
                    "pnl": 100,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "desk_positions_advice.service.generate_advice_llm",
        lambda facts, session_kind, llm_call=None: {
            "status": "ok",
            "items": [{"symbol": "600000.SH", "action": "持有", "reason": "稳"}],
            "market_note": None,
        },
    )
    out = advise_advice(db, session_kind="closing", asof=date(2026, 7, 27), picks=[])
    assert out["status"] == "ok"
    assert out["items"][0]["action"] == "持有"
```

- [ ] **Step 2: 实现 service.py**

```python
"""持仓建议编排。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_positions_advice.format import append_advice_section
from desk_positions_advice.llm import generate_advice_llm
from desk_positions_advice.positions import load_positions, truncate_positions
from desk_positions_advice.rules import rule_candidates

logger = logging.getLogger(__name__)


def advise_advice(
    db: Session,
    *,
    session_kind: str,
    asof: date,
    picks: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    llm_call=None,
) -> dict[str, Any]:
    """
    生成持仓建议结构化结果（供拼推送与写入 extras）。

    @param session_kind: morning | closing
    @param picks: 本次选股命中列表（可选）
    @param context: 情绪/竞价等附加上下文
    """
    settings = get_settings()
    if not getattr(settings, "positions_advice_enabled", True):
        return {"status": "disabled", "source": settings.positions_advice_source, "items": []}

    source = getattr(settings, "positions_advice_source", "live") or "live"
    mode = getattr(settings, "positions_advice_mode", "llm") or "llm"

    loaded = load_positions(db, source)
    if not loaded.get("ok"):
        err = loaded.get("error") or loaded.get("message") or "读仓失败"
        return {
            "status": "error",
            "source": source,
            "items": [],
            "section": f"持仓建议生成失败：{err}",
            "error": err,
        }

    positions = list(loaded.get("positions") or [])
    if not positions:
        return {
            "status": "empty",
            "source": source,
            "items": [],
            "section": "当前无持仓，跳过建议",
        }

    positions, truncated = truncate_positions(positions)

    pick_symbols = {
        str(p.get("symbol") or p.get("code") or "")
        for p in (picks or [])
        if isinstance(p, dict)
    }
    for p in positions:
        p["in_picks"] = p.get("symbol") in pick_symbols

    rule_cands: list[dict[str, Any]] = []
    if mode == "hybrid":
        try:
            rule_cands = rule_candidates(positions, session_kind=session_kind)
        except Exception:  # noqa: BLE001
            logger.exception("rule_candidates failed; degrade to llm")
            rule_cands = []

    facts: dict[str, Any] = {
        "asof": asof.isoformat(),
        "session_kind": session_kind,
        "mode": mode,
        "positions": positions,
        "picks_sample": (picks or [])[:12],
        "context": context or {},
    }
    if rule_cands:
        facts["rule_candidates"] = rule_cands

    llm_out = generate_advice_llm(facts, session_kind=session_kind, llm_call=llm_call)
    if llm_out.get("status") != "ok":
        err = llm_out.get("error") or "未知错误"
        return {
            "status": "error",
            "source": source,
            "items": [],
            "section": f"持仓建议生成失败：{err}",
            "error": err,
            "truncated": truncated,
        }

    return {
        "status": "ok",
        "source": source,
        "mode": mode,
        "items": llm_out.get("items") or [],
        "market_note": llm_out.get("market_note"),
        "truncated": truncated,
        "rule_candidates": rule_cands or None,
    }


# 供挂点方便使用
__all__ = ["advise_advice", "append_advice_section"]
```

更新 `__init__.py` 导出 `advise_advice`。

- [ ] **Step 3: 跑全文件测试**

Run: `python -m pytest tests/test_positions_advice.py -v`  
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add packages/positions_advice tests/test_positions_advice.py
git commit -m "feat: advise_advice 编排持仓建议"
```

---

### Task 7: 挂接尾盘选股

**Files:**
- Modify: `packages/closing_pick/desk_closing_pick/__init__.py`
- Modify: `tests/test_closing_pick.py`（追加 1 个用例）

- [ ] **Step 1: 调整 `ClosingPickService.run`**

在拼好选股 `content` / `extras` 之后、`_store_brief` 与 `alert.send` **之前**：

```python
        from desk_positions_advice import advise_advice, append_advice_section

        advice = advise_advice(
            self.db,
            session_kind="closing",
            asof=asof,
            picks=stocks,
        )
        if advice.get("status") != "disabled":
            content = append_advice_section(content, advice)
            extras["positions_advice"] = {
                k: advice.get(k)
                for k in (
                    "status",
                    "source",
                    "mode",
                    "items",
                    "market_note",
                    "truncated",
                    "error",
                    "section",
                )
                if advice.get(k) is not None
            }
```

注意：无策略提前 return 的路径也可按需跳过建议（YAGNI：无策略时可不附建议；与「选股照推」不冲突）。首版：**有策略扫描路径**挂接即可；无策略 early return 保持原样。

确保 `_store_brief` 使用更新后的 `content`/`extras`，且飞书 `send` 使用同一 `content`。

- [ ] **Step 2: 挂点测试**

在 `tests/test_closing_pick.py` 追加（沿用现有 fixture）：

```python
def test_closing_run_appends_positions_advice(db, monkeypatch):
    monkeypatch.setattr(
        "desk_closing_pick.advise_advice",
        lambda *a, **k: {
            "status": "empty",
            "source": "live",
            "section": "当前无持仓，跳过建议",
            "items": [],
        },
    )
    # 若 import 在函数内，改为 monkeypatch desk_positions_advice.advise_advice
    monkeypatch.setattr(
        "desk_positions_advice.advise_advice",
        lambda *a, **k: {
            "status": "empty",
            "source": "live",
            "section": "当前无持仓，跳过建议",
            "items": [],
        },
    )
    # …构造最小可 run 环境（可复用已有 test 的建策略/日历手法）…
    # assert "持仓建议" in report.content
```

实现时：优先 `monkeypatch.setattr("desk_positions_advice.service.advise_advice", ...)` 或在 closing 模块绑定名上 patch；以实际 import 方式为准。断言 `report.content` 含「持仓建议」与「无持仓」。

若现有测试因飞书/LLM 变慢，保持 advice mock，避免真调 LLM。

- [ ] **Step 3: 跑测**

Run: `python -m pytest tests/test_closing_pick.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add packages/closing_pick/desk_closing_pick/__init__.py tests/test_closing_pick.py
git commit -m "feat: 尾盘选股推送附带持仓建议"
```

---

### Task 8: 挂接早盘竞价强势

**Files:**
- Modify: `packages/morning_brief/desk_morning_brief/__init__.py`
- Modify: `tests/test_morning_rest_day.py` 或新建短测

- [ ] **Step 1: 在 `run_post_auction` 挂接**

在拼好 `content` 之后、`_store` 与 `alert.send` 之前（有快照成功路径）：

```python
        from desk_positions_advice import advise_advice, append_advice_section
        from desk_sentiment import SentimentService

        ctx: dict = {}
        try:
            ctx["sentiment"] = SentimentService(self.db).snapshot(asof)
        except Exception:  # noqa: BLE001
            pass
        advice = advise_advice(
            self.db,
            session_kind="morning",
            asof=asof,
            picks=stocks,
            context={**ctx, "boards": boards},
        )
        extras = {
            "boards": boards,
            "stocks": stocks,
            **(
                {"day_note": day_note.strip(), "requested_asof": requested.isoformat()}
                if day_note
                else {}
            ),
        }
        if advice.get("status") != "disabled":
            content = append_advice_section(content, advice)
            extras["positions_advice"] = {
                k: advice.get(k)
                for k in (
                    "status",
                    "source",
                    "mode",
                    "items",
                    "market_note",
                    "truncated",
                    "error",
                    "section",
                )
                if advice.get(k) is not None
            }
        self._store(asof, "post_auction", content, extras)
        self.alert.send(
            "早盘·竞价强势", content, category="morning", dedupe_key=f"auction:{asof}"
        )
```

重构时注意：当前代码先 `_store` 再 `send`；改为**先拼 advice，再 store+send**。无快照 early return 路径不挂建议。

- [ ] **Step 2: 测试**

Mock `advise_advice`，跑 `run_post_auction`（有假 `AuctionSnapshot` 或沿用现有休息日测），断言 content 含持仓建议段；或仅单测 monkeypatch 后检查 extras。

Run: `python -m pytest tests/test_morning_rest_day.py tests/test_positions_advice.py -v`

- [ ] **Step 3: Commit**

```bash
git add packages/morning_brief/desk_morning_brief/__init__.py tests/
git commit -m "feat: 早盘竞价推送附带持仓建议"
```

---

### Task 9: Settings UI

**Files:**
- Modify: `apps/web/src/pages/Settings.tsx`

- [ ] **Step 1: 扩展类型与默认值**

在 `AppSettings` / `emptyForm` 增加：

```typescript
  positions_advice_enabled?: boolean;
  positions_advice_mode?: "llm" | "hybrid";
  positions_advice_source?: "live" | "paper";
```

默认：`positions_advice_enabled: true`，`positions_advice_mode: "llm"`，`positions_advice_source: "live"`。

- [ ] **Step 2: 保存 payload**

在 save body 中加入这三项（与 `review_auto` 并列）。

- [ ] **Step 3: UI**

在「投研精选 / 复盘」相关 Tab（`review_auto` 复选框附近）增加：

```tsx
<label className="flex items-start gap-2 text-sm text-[var(--desk-text)]">
  <input
    type="checkbox"
    className="mt-1"
    checked={Boolean(form.positions_advice_enabled)}
    onChange={(e) => patch("positions_advice_enabled", e.target.checked)}
  />
  <span>
    早盘/尾盘选股附带持仓建议
    <span className="mt-0.5 block text-xs text-[var(--desk-mist)]">
      与选股同一条飞书推送；需 LLM Key；失败不影响选股结果
    </span>
  </span>
</label>
<Field label="持仓建议模式">
  <select
    className={inputClass}
    value={form.positions_advice_mode || "llm"}
    onChange={(e) =>
      patch("positions_advice_mode", e.target.value as "llm" | "hybrid")
    }
  >
    <option value="llm">纯 LLM</option>
    <option value="hybrid">规则候选 + LLM</option>
  </select>
</Field>
<Field label="持仓来源">
  <select
    className={inputClass}
    value={form.positions_advice_source || "live"}
    onChange={(e) =>
      patch("positions_advice_source", e.target.value as "live" | "paper")
    }
  >
    <option value="live">实盘 Live</option>
    <option value="paper">纸交易 Paper</option>
  </select>
</Field>
```

样式类名与邻近控件保持一致。

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/Settings.tsx
git commit -m "feat: Settings 持仓建议开关与模式"
```

---

### Task 10: 文档收尾

**Files:**
- Modify: `docs/TODO.md`（可选一行后续/已完成）
- Modify: `docs/superpowers/specs/2026-07-27-positions-advice-design.md` 状态改为「已实现」（全部测通后）

- [ ] **Step 1: 全量相关测试**

```bash
python -m pytest tests/test_positions_advice.py tests/test_closing_pick.py tests/test_morning_rest_day.py -q
```

Expected: PASS

- [ ] **Step 2: 更新 spec 状态为已实现；TODO 勾选（若有条目）**

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-07-27-positions-advice-design.md docs/TODO.md
git commit -m "docs: 持仓建议规格标为已实现"
```

---

## Self-Review (plan vs spec)

| Spec 要求 | Task |
|-----------|------|
| 共享模块 positions_advice | 2–6 |
| 模式 llm/hybrid | 1, 4, 6 |
| 持仓源 live/paper 默认 live | 1, 3 |
| 仅 post_auction + closing | 7, 8 |
| 动作枚举分场景 | 2, 5 |
| 失败选股仍推 | 6–8 |
| extras.positions_advice | 7, 8 |
| Settings UI | 9 |
| 截断 20 | 3 |
| 测试清单 | 2–8 |

无 TBD 占位；`load_positions` 的 Broker 类名需实现时与 `desk_broker` 对齐（Task 3 已注明核对）。
