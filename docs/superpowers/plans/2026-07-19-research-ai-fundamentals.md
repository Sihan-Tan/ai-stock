# 投研基本面 / 估值 / 五步法 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Desk 原生 Agent + Skills 上交付基本面分析、同行对比、估值与五步法研报；财务数据 QMT 优先、akshare 降级并缓存。

**Architecture:** `FinancialService`（`packages/market`）统一取数与标准化；`NanobotResearchSession` 改为 OpenAI tools 循环并注册只读工具；`skills/` 新增五份投研 skill；`Research.tsx` 多轮流式 + 快捷提示。不嵌入 Charles / Gradio。

**Tech Stack:** FastAPI、SQLAlchemy、xtquant（可选）、akshare、OpenAI SDK、React/HeroUI、pytest、vitest

**Spec:** `docs/superpowers/specs/2026-07-19-research-ai-fundamentals-design.md`

---

## File Structure

| 路径 | 职责 |
|------|------|
| `packages/db/desk_db/models.py` | 新增 `FinancialSnapshot` |
| `alembic/versions/0006_financial_snapshots.py` | 迁移 |
| `packages/market/desk_market/qmt_financials.py` | QMT 财务 Protocol + Mock + Xtdata 实现 |
| `packages/market/desk_market/akshare_financials.py` | akshare 财务拉取 → 标准 payload |
| `packages/market/desk_market/financials.py` | `FinancialService`：缓存 / 降级 / 对比 / 估值 |
| `packages/ai/desk_ai/skills.py` | 从 `__init__.py` 抽出 `SkillLoader` |
| `packages/ai/desk_ai/tools.py` | OpenAI tools schema + `dispatch_tool` |
| `packages/ai/desk_ai/web_search.py` | Tavily（`TAVILY_API_KEY`） |
| `packages/ai/desk_ai/session.py` | `NanobotResearchSession` tools 循环 |
| `packages/ai/desk_ai/__init__.py` | 再导出 |
| `packages/common/desk_common/settings.py` | 可选 `tavily_api_key`（env `TAVILY_API_KEY`） |
| `apps/api/app/routes/ai.py` | `skill_hint`、`GET /financials/{symbol}` |
| `skills/investment-research/SKILL.md` 等 5 个 | 投研 skills |
| `apps/web/src/pages/Research.tsx` | 多轮流式 UI |
| `tests/test_financials.py` | 财务服务 / API |
| `tests/test_ai_tools_session.py` | tools + mock LLM 循环 |
| `apps/web/src/pages/Research.test.tsx`（可选）或纯函数测 messages 组装 | 前端轻量 |

**锁定决策（实现时勿再争论）：**

- 财务包路径：`packages/market`（不新建 `packages/research`）
- `save_research_note` → `KnowledgeStore.upsert(..., doc_type="research_note", tags=symbols)`
- 搜索：仅 env / settings `tavily_api_key`，本期不强制改 Settings UI（README 注明即可）
- 符号一律 `normalize_symbol`（`600519.SH`）；akshare 内部转 6 位代码

---

### Task 1: FinancialSnapshot 模型 + 迁移

**Files:**
- Modify: `packages/db/desk_db/models.py`
- Create: `alembic/versions/0006_financial_snapshots.py`
- Test: `tests/test_financials.py`（先写模型可写入）

- [ ] **Step 1: 在 models.py 末尾附近新增模型**

```python
class FinancialSnapshot(Base):
    """财务快照缓存（投研）。"""

    __tablename__ = "financial_snapshots"
    __table_args__ = (
        UniqueConstraint("symbol", "table_name", "period", name="uq_financial_snap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    table_name: Mapped[str] = mapped_column(String(32))  # Balance|Income|CashFlow|Pershareindex|Capital|Abstract
    period: Mapped[str] = mapped_column(String(16))  # YYYYMMDD 报告期
    source: Mapped[str] = mapped_column(String(16))  # qmt|akshare
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

确保文件顶部已 import `UniqueConstraint`（若尚未）。

- [ ] **Step 2: 写 alembic 0006**

```python
"""financial_snapshots 缓存表。"""
revision: str = "0006_financial_snapshots"
down_revision = "0005_strategy_lifecycle"

def upgrade() -> None:
    op.create_table(
        "financial_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("table_name", sa.String(length=32), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "table_name", "period", name="uq_financial_snap"),
    )
    op.create_index("ix_financial_snapshots_symbol", "financial_snapshots", ["symbol"])

def downgrade() -> None:
    op.drop_index("ix_financial_snapshots_symbol", table_name="financial_snapshots")
    op.drop_table("financial_snapshots")
```

- [ ] **Step 3: 测试可 create_all 写入一行**

```python
def test_financial_snapshot_roundtrip(db_session):
    from desk_db.models import FinancialSnapshot
    import json
    from datetime import datetime

    row = FinancialSnapshot(
        symbol="600519.SH",
        table_name="Abstract",
        period="20241231",
        source="qmt",
        payload_json=json.dumps({"roe": 30.1}),
        fetched_at=datetime.utcnow(),
    )
    db_session.add(row)
    db_session.flush()
    assert row.id is not None
```

复用项目现有 session fixture；若无，在 `tests/test_financials.py` 内用内存 SQLite + `Base.metadata.create_all`（对齐 `tests/test_core.py`）。

- [ ] **Step 4: Commit**

```bash
git add packages/db/desk_db/models.py alembic/versions/0006_financial_snapshots.py tests/test_financials.py
git commit -m "feat(db): 新增 financial_snapshots 缓存表"
```

---

### Task 2: QMT / akshare 财务适配（可 mock）

**Files:**
- Create: `packages/market/desk_market/qmt_financials.py`
- Create: `packages/market/desk_market/akshare_financials.py`
- Modify: `tests/test_financials.py`

- [ ] **Step 1: 写失败测试 — Mock 源返回标准结构**

```python
def test_mock_qmt_financials_returns_tables():
    from desk_market.qmt_financials import MockQmtFinancials

    src = MockQmtFinancials(
        data={
            "600519.SH": {
                "Income": [{"period": "20241231", "revenue": 1e11, "net_profit": 5e10}],
                "Pershareindex": [{"period": "20241231", "roe": 30.0, "eps": 50.0}],
            }
        }
    )
    out = src.get_financials("600519.SH", tables=["Income", "Pershareindex"])
    assert out["source"] == "qmt"
    assert out["tables"]["Income"][0]["net_profit"] == 5e10
```

- [ ] **Step 2: 实现 Protocol + Mock**

`qmt_financials.py` 要点：

```python
class QmtFinancials(Protocol):
    def get_financials(self, symbol: str, tables: list[str], years: int = 5) -> dict[str, Any]:
        """返回 {source, symbol, tables: {name: [row...]}} 或抛异常。"""
        ...

class MockQmtFinancials:
    def __init__(self, data: dict | None = None, *, fail: bool = False): ...
    def get_financials(self, symbol: str, tables: list[str], years: int = 5) -> dict[str, Any]: ...

class XtdataFinancials:
    """本机 QMT；download_financial_data + get_financial_data；字段映射到标准 key。"""
    def get_financials(self, symbol: str, tables: list[str], years: int = 5) -> dict[str, Any]: ...
```

标准 row keys（最少）：`period`, `revenue`, `net_profit`, `gross_margin`, `net_margin`, `roe`, `debt_ratio`, `eps`, `bps`, `operating_cashflow`, `total_assets`, `total_liab`, `total_equity`, `total_shares`。映射时对 QMT 中英文列名做别名表；缺失字段填 `null`。

- [ ] **Step 3: akshare 适配**

`akshare_financials.py`：

```python
def fetch_akshare_financials(symbol: str, years: int = 5) -> dict[str, Any]:
    """
    用 akshare 拉财务摘要等，归一为与 QMT 相同 tables 结构；source=akshare。
    代码：normalize 后取 6 位。失败 raise RuntimeError。
    """
```

CI 中默认不打真网：单测用 `monkeypatch.setattr("desk_market.akshare_financials._raw_fetch", lambda *a, **k: {...})`。

- [ ] **Step 4: pytest 通过后 commit**

```bash
git add packages/market/desk_market/qmt_financials.py packages/market/desk_market/akshare_financials.py tests/test_financials.py
git commit -m "feat(market): QMT/akshare 财务适配与 Mock"
```

---

### Task 3: FinancialService（缓存 / 降级 / 对比 / 估值）

**Files:**
- Create: `packages/market/desk_market/financials.py`
- Modify: `tests/test_financials.py`

- [ ] **Step 1: 失败测试 — 缓存命中不调 QMT**

```python
def test_financial_service_uses_cache(db_session, monkeypatch):
    from desk_market.financials import FinancialService
    from desk_market.qmt_financials import MockQmtFinancials
    import json
    from datetime import datetime
    from desk_db.models import FinancialSnapshot

    db_session.add(
        FinancialSnapshot(
            symbol="600519.SH",
            table_name="Abstract",
            period="20241231",
            source="qmt",
            payload_json=json.dumps({"roe": 31.0, "period": "20241231"}),
            fetched_at=datetime.utcnow(),
        )
    )
    db_session.flush()
    called = {"n": 0}

    class Boom(MockQmtFinancials):
        def get_financials(self, *a, **k):
            called["n"] += 1
            raise AssertionError("should not call")

    svc = FinancialService(db_session, qmt=Boom(), akshare_fetch=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")))
    out = svc.get_financials("600519", years=5)
    assert out["source"] == "qmt"
    assert called["n"] == 0
    assert any(r.get("roe") == 31.0 for r in out["metrics"])
```

- [ ] **Step 2: 失败测试 — QMT 失败降级 akshare**

```python
def test_financial_service_fallback_akshare(db_session):
    from desk_market.financials import FinancialService
    from desk_market.qmt_financials import MockQmtFinancials

    def fake_ak(symbol, years=5):
        return {
            "source": "akshare",
            "symbol": "600519.SH",
            "tables": {"Abstract": [{"period": "20241231", "roe": 28.0}]},
        }

    svc = FinancialService(
        db_session,
        qmt=MockQmtFinancials(fail=True),
        akshare_fetch=fake_ak,
        ttl_days=7,
    )
    out = svc.get_financials("600519.SH")
    assert out["source"] == "akshare"
    assert out["metrics"][0]["roe"] == 28.0
```

- [ ] **Step 3: 实现 FinancialService**

```python
class FinancialService:
    def __init__(self, db, qmt=None, akshare_fetch=None, ttl_days=7, market: MarketService | None = None):
        ...

    def get_financials(self, symbol: str, years: int = 5) -> dict:
        """缓存 → qmt → akshare；返回 {symbol, source, metrics: [...], tables?, error?}"""

    def peer_compare(self, symbols: list[str], years: int = 5) -> dict:
        """批量 get_financials，拼 latest 指标表 + missing[]"""

    def get_valuation(self, symbol: str, peers: list[str] | None = None) -> dict:
        """
        现价：MarketService 最新 quote/close；
        PE ≈ price/eps，PB ≈ price/bps（缺字段则 null）；
        历史分位：同 symbol 缓存多期 PE 序列，样本 <3 则 percentile=null 并 note；
        peers 非空则相对中位数。
        """
```

构造默认：`qmt` 尝试 `XtdataFinancials()`，失败用 `MockQmtFinancials(fail=True)` 以便走 akshare；`akshare_fetch` 默认 `fetch_akshare_financials`。

- [ ] **Step 4: 双失败返回 error 结构（不抛到 API 外未处理）**

```python
def test_financial_service_both_fail(db_session):
    svc = FinancialService(db_session, qmt=MockQmtFinancials(fail=True), akshare_fetch=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = svc.get_financials("600519.SH")
    assert "error" in out
```

- [ ] **Step 5: Commit**

```bash
git add packages/market/desk_market/financials.py tests/test_financials.py
git commit -m "feat(market): FinancialService 缓存与 QMT→akshare 降级"
```

---

### Task 4: 调试 API `GET /api/ai/financials/{symbol}`

**Files:**
- Modify: `apps/api/app/routes/ai.py`
- Modify: `tests/test_financials.py` 或 `tests/test_core.py`

- [ ] **Step 1: 路由**

```python
@router.get("/financials/{symbol}")
def financials(symbol: str, years: int = 5, db: Session = Depends(get_db)):
    from desk_market.financials import FinancialService
    return FinancialService(db).get_financials(symbol, years=years)
```

- [ ] **Step 2: API 测试（monkeypatch FinancialService.get_financials）**

```python
def test_ai_financials_api(client, monkeypatch):
    monkeypatch.setattr(
        "desk_market.financials.FinancialService.get_financials",
        lambda self, symbol, years=5: {"symbol": "600519.SH", "source": "qmt", "metrics": [{"roe": 1}]},
    )
    r = client.get("/api/ai/financials/600519?years=3")
    assert r.status_code == 200
    assert r.json()["source"] == "qmt"
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/routes/ai.py tests/test_financials.py
git commit -m "feat(api): 投研财务调试接口 GET /api/ai/financials"
```

---

### Task 5: 拆分 desk_ai + tools 注册表

**Files:**
- Create: `packages/ai/desk_ai/skills.py`（移入 `SkillLoader`）
- Create: `packages/ai/desk_ai/tools.py`
- Create: `packages/ai/desk_ai/web_search.py`
- Modify: `packages/ai/desk_ai/__init__.py`
- Create: `tests/test_ai_tools_session.py`
- Modify: `packages/common/desk_common/settings.py` — 增加 `tavily_api_key: str = ""`（Field env `TAVILY_API_KEY`）

- [ ] **Step 1: TOOL_SPECS + dispatch 测试**

```python
def test_dispatch_unknown_tool(db_session):
    from desk_ai.tools import dispatch_tool
    assert dispatch_tool(db_session, "place_order", {})["error"].startswith("unknown")

def test_dispatch_get_financials(db_session, monkeypatch):
    monkeypatch.setattr(
        "desk_market.financials.FinancialService.get_financials",
        lambda self, symbol, years=5: {"symbol": symbol, "source": "qmt", "metrics": []},
    )
    from desk_ai.tools import dispatch_tool
    out = dispatch_tool(db_session, "get_financials", {"symbol": "600519"})
    assert out["source"] == "qmt"
```

- [ ] **Step 2: 实现 tools.py**

允许的工具名（白名单）：

`get_watchlist`, `list_strategies`, `list_skills`, `search_knowledge`, `save_strategy_draft`,
`get_financials`, `peer_compare`, `get_valuation`, `web_search`, `save_research_note`

```python
TOOL_SPECS: list[dict]  # OpenAI tools 格式 function schema

def dispatch_tool(db: Session, name: str, arguments: dict) -> Any:
    if name not in ALLOWED:
        return {"error": f"unknown tool {name}"}
    # get_financials → FinancialService(db).get_financials(...)
    # peer_compare → ...
    # get_valuation → ...
    # web_search → desk_ai.web_search.search(query)
    # save_research_note → KnowledgeStore(db).upsert(title, body, doc_type="research_note", tags=",".join(symbols or []))
    # 其余保持 NanobotResearchSession 旧逻辑
```

`web_search.py`：无 key 返回 `{"error": "tavily_api_key not configured"}`；有 key 则 `https://api.tavily.com/search` POST（用 `httpx` 或 `urllib`，与项目已有 HTTP 客户端一致）。

- [ ] **Step 3: settings 增加 tavily_api_key**

```python
tavily_api_key: str = ""  # env TAVILY_API_KEY
```

- [ ] **Step 4: Commit**

```bash
git add packages/ai/desk_ai packages/common/desk_common/settings.py tests/test_ai_tools_session.py
git commit -m "feat(ai): 投研只读 tools 白名单与 Tavily 搜索"
```

---

### Task 6: NanobotResearchSession tools 循环

**Files:**
- Create: `packages/ai/desk_ai/session.py`
- Modify: `packages/ai/desk_ai/__init__.py` 导出
- Modify: `tests/test_ai_tools_session.py`
- Modify: `tests/test_core.py` 中 `test_morning_and_ai_skills`（若断言过时则更新）

- [ ] **Step 1: mock LLM 触发 tool_calls 的测试**

用可注入的 `client` 或 monkeypatch `AsyncOpenAI`：

```python
@pytest.mark.asyncio
async def test_session_tools_loop_one_round(db_session, monkeypatch):
    from desk_ai.session import NanobotResearchSession

    class Msg:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class Choice:
        def __init__(self, message):
            self.message = message

    class Resp:
        def __init__(self, message):
            self.choices = [Choice(message)]

    class FakeTC:
        def __init__(self, id, name, arguments):
            self.id = id
            self.type = "function"
            self.function = type("F", (), {"name": name, "arguments": arguments})()

    calls = {"n": 0}

    async def fake_create(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return Resp(Msg(tool_calls=[FakeTC("1", "get_financials", '{"symbol":"600519.SH"}')]))
        return Resp(Msg(content="ROE 来自工具结果，财务稳健。"))

    # monkeypatch session 内部 _chat_create = fake_create
    session = NanobotResearchSession(db_session)
    monkeypatch.setattr(session, "_chat_create", fake_create)
    monkeypatch.setenv("LLM_API_KEY", "test")
    from desk_common.settings import get_settings
    get_settings.cache_clear()
    # 若 settings 从 DB/env 读，确保 llm_api_key 非空：monkeypatch.setattr(session.settings, "llm_api_key", "x")

    chunks = []
    async for c in session.run([{"role": "user", "content": "茅台财务怎么样"}], skill_hint="financial-analysis"):
        chunks.append(c)
    text = "".join(chunks)
    assert "get_financials" in text or "ROE" in text
    assert calls["n"] >= 2
```

- [ ] **Step 2: 实现 session.py**

行为：

1. `skill_hint` 若提供：`skills.load(hint)` 拼进 system（失败则忽略）
2. system 固定包含：身份、skills 摘要、`数字必须来自工具`、`禁止下单`
3. `messages` 复制后循环：`max_iterations=8`
4. 每次 `_chat_create(model, messages, tools=TOOL_SPECS, tool_choice="auto")`
5. 若 `tool_calls`：yield `[tool:{name}]\n`，`dispatch_tool`，把 `role=tool` 结果 append；结果 JSON 截断至约 12_000 字符
6. 若最终 `content`：yield content 并 return
7. 无 `llm_api_key`：yield 提示去设置页 LLM；可保留旧规则降级（策略/知识关键词），但**不要**假装完成五步法

把原 `__init__.py` 中类移到 `session.py`，`__init__.py`：

```python
from desk_ai.skills import SkillLoader
from desk_ai.session import NanobotResearchSession
__all__ = ["SkillLoader", "NanobotResearchSession"]
```

- [ ] **Step 3: 更新 ai 路由接受 skill_hint**

```python
class ChatIn(BaseModel):
    messages: list[dict]
    skill_hint: str | None = None

async def chat(body: ChatIn, db: Session = Depends(get_db)):
    session = NanobotResearchSession(db)
    async def gen():
        async for chunk in session.run(body.messages, skill_hint=body.skill_hint):
            yield chunk
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
```

- [ ] **Step 4: Commit**

```bash
git add packages/ai/desk_ai apps/api/app/routes/ai.py tests/test_ai_tools_session.py tests/test_core.py
git commit -m "feat(ai): 投研 Agent OpenAI tools 循环"
```

---

### Task 7: 五个投研 Skills

**Files:**
- Create: `skills/investment-research/SKILL.md`
- Create: `skills/financial-analysis/SKILL.md`
- Create: `skills/peer-compare/SKILL.md`
- Create: `skills/valuation/SKILL.md`
- Create: `skills/write-report/SKILL.md`
- Modify: `tests/test_core.py` 或 `tests/test_ai_tools_session.py` — 断言 skills 列表包含新名字

每个文件 frontmatter + 正文。要点（正文必须写清工具名，禁止 exec 脚本路径）：

**investment-research：** 场景路由表（财务→financial-analysis；对比→peer-compare；估值→valuation；研报/五步法→write-report）。

**financial-analysis：** 先 `get_financials`，再解读毛利率/ROE/负债/现金流；无数据则说明 error。

**peer-compare：** `peer_compare`，symbols 逗号或列表。

**valuation：** `get_valuation`，可带 peers。

**write-report：** 五步法（业务/壁垒/预期差/风险/估值）；顺序建议 `get_financials` → `get_valuation` → `web_search`（可失败）→ `search_knowledge` → 成文；可选 `save_research_note`。

- [ ] **Step 1: 写入 5 个 SKILL.md**
- [ ] **Step 2: `GET /api/ai/skills` 测试包含 `write-report` 与 `financial-analysis`**
- [ ] **Step 3: Commit**

```bash
git add skills tests/test_ai_tools_session.py
git commit -m "feat(skills): 投研基本面/对比/估值/五步法 skills"
```

---

### Task 8: Research 前端多轮流式

**Files:**
- Modify: `apps/web/src/pages/Research.tsx`
- Modify: `apps/web/src/layout/nav.ts` — label 可改为 `投研`（可选）
- Optional: `apps/web/src/pages/researchMessages.ts` + vitest（组装 messages 纯函数）

- [ ] **Step 1: 纯函数（可选但推荐）**

```typescript
/** 将历史与用户输入组装为 API messages */
export function buildChatMessages(
  history: Array<{ role: "user" | "assistant"; content: string }>,
  userText: string,
): Array<{ role: string; content: string }> {
  return [...history.map((m) => ({ role: m.role, content: m.content })), { role: "user", content: userText }];
}
```

- [ ] **Step 2: 重写 Research.tsx**

布局：

- 左：skills 列表；若 `GET /api/settings` 无 llm key 则 Chip「未配置 LLM」
- 右：消息列表；`pre`/`whitespace-pre-wrap` 渲染；流式用 `ReadableStream` + `TextDecoder` 追加 assistant 气泡
- 快捷按钮设置 `question` 或直接发送，并可带 `skill_hint`
- 「新会话」清空 `history`
- `POST /api/ai/chat` body: `{ messages, skill_hint? }`

快捷文案示例：

1. 帮我用五步法分析贵州茅台 (600519)
2. 中芯国际 (688981) 最近财务与估值是否合理？
3. 比亚迪 vs 长城汽车横向对比
4. 宁德时代护城河与竞争对手（可走 write-report）

- [ ] **Step 3: 手动或 vitest 确认 buildChatMessages**
- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/Research.tsx apps/web/src/layout/nav.ts apps/web/src/pages/researchMessages.ts apps/web/src/pages/researchMessages.test.ts
git commit -m "feat(web): 投研页多轮流式对话与快捷提示"
```

---

### Task 9: 文档与硬规则核对

**Files:**
- Modify: `README.md` — 投研段落：财务 QMT→akshare、skills 列表、`TAVILY_API_KEY`、调试 API
- Modify: `docs/hard-rules.md` — 若需补「财务工具只读」一句（已有禁下单则核对即可）
- Modify: `docs/superpowers/specs/2026-07-19-research-ai-fundamentals-design.md` — 状态改为「实现中」或完成后「已完成」

- [ ] **Step 1: 更新 README 投研小节**
- [ ] **Step 2: 跑全量相关测试**

```bash
pytest tests/test_financials.py tests/test_ai_tools_session.py tests/test_core.py -q
cd apps/web && npm test -- --run src/pages/researchMessages.test.ts
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/hard-rules.md docs/superpowers/specs/2026-07-19-research-ai-fundamentals-design.md
git commit -m "docs(research): 投研财务与 skills 使用说明"
```

---

## Spec 覆盖自检

| Spec 要求 | Task |
|-----------|------|
| FinancialService 缓存/QMT/akshare | 1–3 |
| 调试 GET financials | 4 |
| tools 白名单 + web_search + save_research_note | 5 |
| Agent tools 循环 + skill_hint | 6 |
| 五个 skills | 7 |
| Research 多轮流式 | 8 |
| 禁下单 / 文档 | 5, 9 |
| 估值/对比 | 3（方法）+ 5（工具）+ 7 |

---

## 验收清单（实现后）

1. 配置 LLM 后四类问法可跑通（数字来自工具标记）
2. 关 QMT 时 akshare 仍能出财务（本机有网）
3. `/api/ai/skills` 含新 skills
4. 无 `place_order` 类工具
5. 无 Tavily 时五步法不崩溃
