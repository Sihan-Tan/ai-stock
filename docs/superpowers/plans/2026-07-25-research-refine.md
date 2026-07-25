# 投研精选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 早盘/尾盘原筛选之后，用投研 skill + LLM 打分取可配置 TopN；页面两段展示；支持手动与自动精选。

**Architecture:** 在 `desk_ai` 新增 `ResearchRefineService`：从 `morning_strong_picks` / `closing_picks` 取候选 → 可注入的同步评分函数（默认走 `NanobotResearchSession` 受控 JSON）→ 过滤置信度 → 落库 `research_picks`。API 暴露 refine；latest 附带结果；设置四项配置；auto 时在选拔服务成功后钩子调用（失败不拖垮主流程）。

**Tech Stack:** FastAPI、SQLAlchemy、`desk_ai`、pydantic-settings、pytest、React

**Spec:** `docs/superpowers/specs/2026-07-25-research-refine-design.md`

**约定：** Commit 步骤仅在用户明确要求提交时执行。代码注释：Python 用 docstring；前端新函数用 JSDoc。

---

## File structure

| 路径 | 职责 |
|------|------|
| `packages/db/desk_db/models.py` | `ResearchPick` ORM |
| `alembic/versions/0010_research_picks.py` | 建表迁移 |
| `packages/common/desk_common/settings.py` + `settings_store.py` | 四项配置 |
| `packages/common/desk_common/contracts.py` | `ResearchPickItem` / `ResearchRefineReport` |
| `packages/ai/desk_ai/refine.py` | `ResearchRefineService` + JSON 解析 |
| `packages/ai/desk_ai/session.py` | `score_pick_json`（受控一轮/多轮，返回 dict） |
| `packages/ai/desk_ai/__init__.py` | 导出 |
| `apps/api/app/routes/settings.py` | SettingsPatch |
| `apps/api/app/routes/morning.py` / `closing.py` | refine + latest |
| `packages/morning_brief/...` / `packages/closing_pick/...` | auto 钩子 |
| `apps/web/src/pages/Settings.tsx` | 配置 UI |
| `apps/web/src/pages/Morning.tsx` / `Closing.tsx` | 精选面板 + 按钮 |
| `apps/web/src/pages/sessionPick/shared.tsx` | 可选共用 `ResearchPicksPanel` |
| `.env.example` | 文档化 |
| `tests/test_research_refine.py` | 过滤/排序/跳过/重跑/mock LLM |

---

### Task 1: ORM + Settings + Contracts

**Files:**
- Modify: `packages/db/desk_db/models.py`
- Create: `alembic/versions/0010_research_picks.py`
- Modify: `packages/common/desk_common/settings.py`
- Modify: `packages/common/desk_common/settings_store.py`
- Modify: `apps/api/app/routes/settings.py`
- Modify: `packages/common/desk_common/contracts.py`
- Modify: `.env.example`

- [ ] **Step 1: 追加 ORM**

在 `ClosingPick` 后：

```python
class ResearchPick(Base):
    """投研精选结果（早盘/尾盘共用）。"""

    __tablename__ = "research_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(16), index=True)  # morning|closing
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    rank: Mapped[int] = mapped_column(Integer, default=0)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: Alembic 0010**

`revision = "0010_research_picks"`，`down_revision = "0009_alerts_status_width"`，`op.create_table("research_picks", ...)` 与 ORM 列一致；downgrade drop。

说明：本地若靠 `create_all`，新表也会在下次 ensure 时出现；仍提交 alembic 与仓库惯例一致。

- [ ] **Step 3: Settings 四字段**

```python
    research_refine_top_n: int = 5
    research_refine_min_confidence: float = 70.0
    research_refine_max_candidates: int = 15
    research_refine_auto: bool = False
```

`EDITABLE_ENV` / `public_settings` / `SettingsPatch` / bool 元组加入 `research_refine_auto`；整数字段在 `apply_settings_patch` 中 clamp：

- `top_n`: `max(1, min(20, int(...)))`
- `max_candidates`: `max(1, min(50, int(...)))`
- `min_confidence`: `max(0.0, min(100.0, float(...)))`

`.env.example`：

```
RESEARCH_REFINE_TOP_N=5
RESEARCH_REFINE_MIN_CONFIDENCE=70
RESEARCH_REFINE_MAX_CANDIDATES=15
RESEARCH_REFINE_AUTO=false
```

- [ ] **Step 4: Contracts**

```python
class ResearchPickItem(BaseModel):
    symbol: str
    name: str = ""
    score: float = 0.0
    confidence: float = 0.0
    rationale: str = ""
    rank: int = 0


class ResearchRefineReport(BaseModel):
    asof: date
    source: Literal["morning", "closing"]
    picks: list[ResearchPickItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    candidates_evaluated: int = 0
```

- [ ] **Step 5: 冒烟**

```bash
python -c "from desk_common.settings import Settings; s=Settings(); print(s.research_refine_top_n, s.research_refine_auto)"
```

Expected: `5 False`

- [ ] **Step 6: Commit**（仅用户要求时）

---

### Task 2: ResearchRefineService + session JSON 评分（TDD）

**Files:**
- Create: `packages/ai/desk_ai/refine.py`
- Modify: `packages/ai/desk_ai/session.py`
- Modify: `packages/ai/desk_ai/__init__.py`
- Create: `tests/test_research_refine.py`

- [ ] **Step 1: 写失败单测**

`tests/test_research_refine.py`（sqlite memory fixture 对齐 `test_feishu_alert` / `test_closing_pick`）：

```python
def test_parse_score_payload_valid():
    from desk_ai.refine import parse_score_payload
    out = parse_score_payload('{"symbol":"600519.SH","score":88,"confidence":90,"rationale":"ok"}', "600519.SH")
    assert out["score"] == 88 and out["confidence"] == 90

def test_parse_score_payload_invalid_skips():
    from desk_ai.refine import parse_score_payload
    assert parse_score_payload("not-json", "600519.SH") is None
    assert parse_score_payload('{"score":120,"confidence":50}', "x") is None

def test_refine_filters_by_confidence_and_top_n(db):
    # 插入 3 只 morning stock picks
    # scorer mock: 返回不同 score/confidence
    # top_n=2, min_confidence=70 → 只 2 只且均 >=70，按 score 降序 rank 1..2
    ...

def test_refine_skips_scorer_failure(db):
    # 一只 scorer 抛错 / 返回 None，其余仍入库

def test_refine_overwrite_same_asof_source(db):
    # 跑两次，第二次条数覆盖第一次
```

- [ ] **Step 2: 跑测确认失败**

`pytest tests/test_research_refine.py -v` → ImportError / fail

- [ ] **Step 3: 实现 `parse_score_payload` + `ResearchRefineService`**

`packages/ai/desk_ai/refine.py` 要点：

```python
def parse_score_payload(text: str, expected_symbol: str) -> dict[str, Any] | None:
    """从模型输出提取 JSON；score/confidence 须在 [0,100]。"""
    # 允许 markdown ```json 包裹：用正则找首个 {...}
    ...

class ResearchRefineService:
    def __init__(self, db: Session, scorer: Callable[..., dict|None] | None = None):
        self.db = db
        self.settings = get_settings()
        self.scorer = scorer  # (symbol, name, context) -> dict|None

    def _default_scorer(self, symbol, name, context) -> dict | None:
        import asyncio
        from desk_ai.session import NanobotResearchSession
        return asyncio.run(NanobotResearchSession(self.db).score_pick_json(symbol, name, context))

    def _candidates(self, source: str, asof: date, limit: int) -> list[dict]:
        if source == "morning":
            rows = select MorningStrongPick where asof and pick_type=="stock" order score desc limit
        else:
            # closing: 按 code 去重，取 max score
            ...
        return [{"symbol", "name", "base_score", ...}]

    def run(self, source: Literal["morning","closing"], asof: date | None = None, *,
            top_n: int | None = None, min_confidence: float | None = None) -> ResearchRefineReport:
        self.settings = get_settings()
        # resolve asof via CalendarService 如休息日（与 morning/closing 一致可选）
        # clear existing research_picks for asof+source
        # for each candidate: call scorer; parse; collect
        # filter confidence; sort score desc; assign rank; persist
        # optional feishu category=research
```

无 API Key 且使用 default scorer：返回 `errors=["llm_api_key_missing"]`，picks=[]。

- [ ] **Step 4: `NanobotResearchSession.score_pick_json`**

```python
async def score_pick_json(self, symbol: str, name: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """
    受控投研评分：启用 investment-research / financial-analysis / valuation；
    要求最终只输出一行 JSON。
    """
    if not self.settings.llm_api_key:
        return None
    prompt = (
        f"对 {symbol}（{name}）做精选评分。上下文：{json.dumps(context, ensure_ascii=False)}。"
        "必须调用只读工具获取依据，禁止编造数字。"
        '最终只输出 JSON：{"symbol","score","confidence","rationale"}，score/confidence 为 0-100。'
    )
    # 复用 run() 收集全文，或非流式 _chat_create 循环后取最后 content
    # 返回 parse_score_payload(full_text, symbol)
```

测试不调用真实 LLM：注入 `scorer=`。

- [ ] **Step 5: 导出并跑通测试**

`pytest tests/test_research_refine.py -v` → PASS

- [ ] **Step 6: Commit**（仅用户要求时）

---

### Task 3: API（morning / closing）

**Files:**
- Modify: `apps/api/app/routes/morning.py`
- Modify: `apps/api/app/routes/closing.py`

- [ ] **Step 1: 共享序列化 helper**（可放在各自文件或 `desk_ai.refine`）

```python
def list_research_picks(db, asof: date, source: str) -> list[dict]:
    rows = db.scalars(
        select(ResearchPick)
        .where(ResearchPick.asof == asof, ResearchPick.source == source)
        .order_by(ResearchPick.rank.asc())
    ).all()
    return [
        {
            "symbol": r.symbol,
            "name": r.name,
            "score": r.score,
            "confidence": r.confidence,
            "rationale": r.rationale,
            "rank": r.rank,
        }
        for r in rows
    ]
```

- [ ] **Step 2: latest 增加字段**

`_latest_payload` / closing 等价物返回增加 `"research_picks": list_research_picks(...)`。

- [ ] **Step 3: POST refine**

```python
class ResearchRefineIn(BaseModel):
    asof: date | None = None
    top_n: int | None = Field(None, ge=1, le=20)
    min_confidence: float | None = Field(None, ge=0, le=100)

@router.post("/research-refine")
def research_refine(body: ResearchRefineIn | None = None, db: Session = Depends(get_db)):
    payload = body or ResearchRefineIn()
    report = ResearchRefineService(db).run(
        "morning",  # closing 路由用 "closing"
        payload.asof,
        top_n=payload.top_n,
        min_confidence=payload.min_confidence,
    )
    db.commit()
    return report.model_dump()
```

无候选时返回空 picks + errors 可选 `no_candidates`。

- [ ] **Step 4: API 烟测（可选小测）**

在 `tests/test_research_refine.py` 用 FastAPI TestClient + mock scorer via monkeypatch `ResearchRefineService._default_scorer` 或构造时注入困难则 patch `refine.ResearchRefineService.run` 仅测路由挂载——优先测 service，路由用轻量：

```python
def test_morning_latest_includes_research_picks_key(client, ...):
    data = client.get("/api/morning/latest").json()
    assert "research_picks" in data
```

- [ ] **Step 5: Commit**（仅用户要求时）

---

### Task 4: 自动精选钩子

**Files:**
- Modify: `packages/morning_brief/desk_morning_brief/__init__.py`
- Modify: `packages/closing_pick/desk_closing_pick/__init__.py`

- [ ] **Step 1: helper**

在 `desk_ai/refine.py`：

```python
def maybe_auto_refine(db: Session, source: str, asof: date) -> None:
    """research_refine_auto 开启时跑精选；异常只记日志。"""
    settings = get_settings()
    if not settings.research_refine_auto:
        return
    if not settings.llm_api_key:
        logger.warning("research_refine_auto 已开但无 LLM Key，跳过")
        return
    try:
        ResearchRefineService(db).run(source, asof)
    except Exception:
        logger.exception("auto research refine failed source=%s asof=%s", source, asof)
```

- [ ] **Step 2: 钩子位置**

- `MorningBriefService.run_post_auction`：在 flush / return **之前**，若 `stocks` 非空则 `maybe_auto_refine(self.db, "morning", asof)`  
- `ClosingPickService.run`：在飞书之后、return 前，若 `stocks` 非空则 `maybe_auto_refine(..., "closing", asof)`

- [ ] **Step 3: 单测 auto**

```python
def test_maybe_auto_refine_respects_flag(db, monkeypatch):
    monkeypatch.setenv("RESEARCH_REFINE_AUTO", "false")
    ...
    # spy run 不被调用
    monkeypatch.setenv("RESEARCH_REFINE_AUTO", "true")
    monkeypatch.setenv("LLM_API_KEY", "x")
    # spy 被调用
```

- [ ] **Step 4: Commit**（仅用户要求时）

---

### Task 5: 前端 Settings + Morning/Closing

**Files:**
- Modify: `apps/web/src/pages/Settings.tsx`
- Modify: `apps/web/src/pages/sessionPick/shared.tsx`（新增 `ResearchPicksPanel`）
- Modify: `apps/web/src/pages/Morning.tsx`
- Modify: `apps/web/src/pages/Closing.tsx`

- [ ] **Step 1: Settings**

`AppSettings` / `EMPTY` / `save` body 增加四字段。飞书 Tab 旁或新小节「投研精选」：

- TopN number input  
- 置信度门槛  
- 候选上限  
- 自动精选 checkbox  

- [ ] **Step 2: shared 面板**

```tsx
/**
 * 投研精选结果表。
 * @param props picks / busy / onRun
 */
export function ResearchPicksPanel({ picks, busy, onRun, emptyHint }: {...}) { ... }
```

列：#、代码、名称、score、confidence、理由。

- [ ] **Step 3: Morning / Closing**

- latest 类型增加 `research_picks`  
- Hero actions 增加「投研精选」→ `POST /api/morning/research-refine`（closing 对应）  
- 原个股表下方渲染 `ResearchPicksPanel`  
- 选拔 `runAll` 成功后若需：再 `loadLatest`（auto 时服务端已写好）

- [ ] **Step 4: Commit**（仅用户要求时）

---

### Task 6: 规格收尾 + 全量相关测试

**Files:**
- Modify: `docs/superpowers/specs/2026-07-25-research-refine-design.md` → 状态「已实现」

- [ ] **Step 1: 跑测**

```bash
pytest tests/test_research_refine.py -v --tb=line
```

Expected: all PASS

- [ ] **Step 2: 更新规格状态**

- [ ] **Step 3: Commit**（仅用户要求时）

---

## Spec coverage

| Spec 项 | Task |
|---------|------|
| research_picks 表 | 1 |
| 四项配置 | 1、5 |
| LLM JSON 打分 + TopN/置信度 | 2 |
| morning/closing API + latest | 3 |
| 手动按钮 | 5 |
| auto 开关钩子 | 4 |
| 两段 UI | 5 |
| 失败不影响原选拔 | 2、4 |
| 单测 | 2、4、6 |

## Self-review notes

- 无 TBD；`ResearchRefineService.run` / `parse_score_payload` / `maybe_auto_refine` 命名前后一致  
- Closing 候选需 **按 symbol 去重**（多策略命中同行）  
- `score_pick_json` 可慢：`max_candidates` 默认 15 控制成本  
- 飞书 `category=research` 为可选；失败不影响精选落库
