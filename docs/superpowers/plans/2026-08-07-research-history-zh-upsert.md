# 投研精选中文来源 + 按日回看 + Upsert 落库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 飞书展示「投研精选·早盘/尾盘」；候选与精选按唯一键 upsert 落库并带 `strategy_id`；早/尾盘页可按日期回看候选+精选。

**Architecture:** 内部 `source` 仍为 `morning`/`closing`，展示用 `research_source_label`；Alembic `0012` 为三表加 `strategy_id`/唯一约束；`ResearchRefineService` 与早/尾盘写入改为 upsert+清理孤儿；前端 Hero 在「投研精选」左侧加日期，`load(asof)` 拉 `latest?asof=`。

**Tech Stack:** Python、SQLAlchemy、Alembic、pytest、React/TypeScript、现有 Morning/Closing UI。

**Spec:** `docs/superpowers/specs/2026-08-07-research-history-zh-upsert-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| Create: `packages/ai/desk_ai/source_label.py` | `research_source_label(source) -> 早盘\|尾盘` |
| Modify: `packages/ai/desk_ai/research_table_image.py` | 顶栏用中文来源 |
| Modify: `packages/ai/desk_ai/refine.py` | 飞书标题/正文、候选带 strategy、upsert 精选、list 返回 strategy_id |
| Modify: `packages/common/desk_common/contracts.py` | `ResearchPickItem.strategy_id` |
| Create: `alembic/versions/0012_research_history_upsert.py` | 列 + 唯一约束 |
| Modify: `packages/db/desk_db/models.py` | ORM 字段与 `__table_args__` |
| Modify: `packages/morning_brief/desk_morning_brief/__init__.py` | 早盘候选 upsert + strategy_id |
| Modify: `packages/closing_pick/desk_closing_pick/__init__.py` | 尾盘候选 upsert |
| Modify: `apps/web/src/pages/sessionPick/shared.tsx` | ResearchPickRow + 策略列（可选） |
| Modify: `apps/web/src/pages/Morning.tsx` | 日期选择 + asof load/refine |
| Modify: `apps/web/src/pages/Closing.tsx` | 同上 |
| Create/Modify: `tests/test_research_source_label.py` 等 | 单测 |
| Modify: spec 状态 → 已实现 | Task 末 |

---

### Task 1: `research_source_label` + 飞书/图片中文

**Files:**
- Create: `packages/ai/desk_ai/source_label.py`
- Modify: `packages/ai/desk_ai/research_table_image.py`
- Modify: `packages/ai/desk_ai/refine.py`（`format_research_feishu_body`、`_maybe_feishu` title）
- Modify: `packages/ai/desk_ai/__init__.py`（可选导出）
- Create: `tests/test_research_source_label.py`
- Modify: `tests/test_research_refine.py` / `tests/test_research_table_image.py`（断言中文）

- [ ] **Step 1: 写失败单测**

```python
"""research_source_label。"""

from desk_ai.source_label import research_source_label


def test_research_source_label_zh():
    assert research_source_label("morning") == "早盘"
    assert research_source_label("closing") == "尾盘"
    assert research_source_label("other") == "other"
```

- [ ] **Step 2: 实现**

```python
"""投研精选 source 对人展示文案。"""

from __future__ import annotations


def research_source_label(source: str) -> str:
    """
    将内部 source 映射为中文展示名。

    @param source morning|closing|其他
    @returns 早盘|尾盘|原样
    """
    s = (source or "").strip().lower()
    if s == "morning":
        return "早盘"
    if s == "closing":
        return "尾盘"
    return source or ""
```

在 `render_research_table_png` 顶栏：

```python
from desk_ai.source_label import research_source_label
label = research_source_label(source)
title = f"投研精选·{label}  {asof}  共 {len(picks)} 只"
```

在 `format_research_feishu_body` / `_maybe_feishu`：

```python
label = research_source_label(source)
# 正文：【投研精选·早盘】...
# 标题：投研精选·早盘
# dedupe_key 仍用英文 source
```

- [ ] **Step 3: 跑测**

```powershell
pytest tests/test_research_source_label.py tests/test_research_table_image.py tests/test_research_refine.py -q -k "feishu_body or source_label or render_png or parse_score"
```

更新既有断言：凡期望含 `morning`/`closing` 展示文案的改为 `早盘`/`尾盘`。

- [ ] **Step 4: Commit**

```powershell
git add packages/ai/desk_ai/source_label.py packages/ai/desk_ai/research_table_image.py packages/ai/desk_ai/refine.py packages/ai/desk_ai/__init__.py tests/test_research_source_label.py tests/test_research_refine.py tests/test_research_table_image.py
$msg = @"
feat(ai): 投研精选飞书展示早盘/尾盘
"@
git commit -m $msg
```

---

### Task 2: 迁移与 ORM（strategy_id + 唯一约束）

**Files:**
- Create: `alembic/versions/0012_research_history_upsert.py`
- Modify: `packages/db/desk_db/models.py`

- [ ] **Step 1: Alembic 0012**

`down_revision = "0011_auction_price"`。

```python
def upgrade() -> None:
    op.add_column("research_picks", sa.Column("strategy_id", sa.String(64), nullable=True))
    op.create_index("ix_research_picks_strategy_id", "research_picks", ["strategy_id"])
    # 去重后建唯一约束（SQLite/Postgres 兼容写法按仓库既有风格）
    op.execute(
        """
        DELETE FROM research_picks
        WHERE id NOT IN (
          SELECT MAX(id) FROM research_picks GROUP BY asof, source, symbol
        )
        """
    )
    op.create_unique_constraint(
        "uq_research_picks_asof_source_symbol",
        "research_picks",
        ["asof", "source", "symbol"],
    )

    op.add_column("morning_strong_picks", sa.Column("strategy_id", sa.String(64), nullable=True))
    op.execute(
        """
        DELETE FROM morning_strong_picks
        WHERE id NOT IN (
          SELECT MAX(id) FROM morning_strong_picks GROUP BY asof, pick_type, code
        )
        """
    )
    op.create_unique_constraint(
        "uq_morning_strong_asof_type_code",
        "morning_strong_picks",
        ["asof", "pick_type", "code"],
    )

    op.execute(
        """
        DELETE FROM closing_picks
        WHERE id NOT IN (
          SELECT MAX(id) FROM closing_picks GROUP BY asof, strategy_id, code
        )
        """
    )
    op.create_unique_constraint(
        "uq_closing_picks_asof_strategy_code",
        "closing_picks",
        ["asof", "strategy_id", "code"],
    )
```

`downgrade`：drop constraint/index/column 对称。

若 SQLite 对 `DELETE … NOT IN (SELECT … GROUP BY)` 有限制，改用 Python 去重脚本或分两步（仓库若已有模式则跟随）。

- [ ] **Step 2: ORM**

`ResearchPick`：加 `strategy_id`；`__table_args__ = (UniqueConstraint("asof","source","symbol", name="uq_research_picks_asof_source_symbol"),)`。

`MorningStrongPick`：加 `strategy_id`；唯一 `(asof, pick_type, code)`。

`ClosingPick`：唯一 `(asof, strategy_id, code)`。

- [ ] **Step 3: 本地 upgrade（开发库）**

```powershell
alembic upgrade head
```

- [ ] **Step 4: Commit**

```powershell
$msg = @"
feat(db): 精选/候选 strategy_id 与唯一约束
"@
git commit -m $msg
```

---

### Task 3: 精选 upsert + 候选带 strategy

**Files:**
- Modify: `packages/common/desk_common/contracts.py`（`ResearchPickItem.strategy_id: str = ""`）
- Modify: `packages/ai/desk_ai/refine.py`
- Modify: `tests/test_research_refine.py`

- [ ] **Step 1: `_candidates` 带上 strategy_id**

早盘候选：每条 `"strategy_id": "auction_strong"`。

尾盘 `best` 合并：保留最高分时同步 `strategy_id=r.strategy_id`。

- [ ] **Step 2: 替换 `_clear`+insert 为 upsert**

```python
def _upsert_picks(self, asof: date, source: str, top: list[dict[str, Any]]) -> list[ResearchPickItem]:
    """按 (asof,source,symbol) upsert；删除本次未入选的同日同源旧行。"""
    keep_symbols: set[str] = set()
    picks: list[ResearchPickItem] = []
    for i, item in enumerate(top, start=1):
        symbol = item["symbol"]
        keep_symbols.add(symbol)
        row = self.db.scalar(
            select(ResearchPick).where(
                ResearchPick.asof == asof,
                ResearchPick.source == source,
                ResearchPick.symbol == symbol,
            )
        )
        sid = str(item.get("strategy_id") or "").strip() or None
        if row is None:
            row = ResearchPick(asof=asof, source=source, symbol=symbol)
            self.db.add(row)
        row.name = item.get("name") or ""
        row.score = float(item["score"])
        row.confidence = float(item["confidence"])
        row.rationale = str(item.get("rationale") or "")
        row.rank = i
        row.strategy_id = sid
        row.meta_json = json.dumps(item.get("meta") or {}, ensure_ascii=False, default=str)
        # flush 后组装 ResearchPickItem（含 strategy_id）
        ...
    # 删孤儿
    orphans = self.db.scalars(
        select(ResearchPick).where(
            ResearchPick.asof == asof,
            ResearchPick.source == source,
            ResearchPick.symbol.not_in(keep_symbols) if keep_symbols else True,
        )
    ).all()
    # 若 keep_symbols 空不应走到这里（上层已 short-circuit）
    for o in orphans:
        if o.symbol not in keep_symbols:
            self.db.delete(o)
    self.db.flush()
    return picks
```

`run()`：成功 top 非空时调用 `_upsert_picks`，删除对 `_clear` 的调用（或 `_clear` 仅用于显式空结果场景，本规格不在无候选时清空）。

`_pack_scored` / 打分结果需把候选上的 `strategy_id` 传到 `top` 项。

- [ ] **Step 3: `list_research_picks` 返回 `strategy_id`**

- [ ] **Step 4: 单测**

```python
def test_refine_upsert_no_duplicate_rows(refine_db, ...):
    # 同一 asof/source/symbol 跑两次 run（mock scorer）
    # assert count == 1；第二次 score 为新值
    # assert strategy_id 有值（closing 或 morning auction_strong）
```

- [ ] **Step 5: Commit**

```powershell
$msg = @"
feat(ai): 投研精选 upsert 并写入 strategy_id
"@
git commit -m $msg
```

---

### Task 4: 早盘/尾盘候选 upsert

**Files:**
- Modify: `packages/morning_brief/desk_morning_brief/__init__.py`
- Modify: `packages/closing_pick/desk_closing_pick/__init__.py`
- Modify: `tests/` 中 morning/closing 相关测（若有写入断言则更新）

- [ ] **Step 1: 早盘**

常量：`MORNING_STOCK_STRATEGY_ID = "auction_strong"`。

替换「删全日再插」：

1. 构建本次 boards+stocks 的 `(pick_type, code)` 集合。
2. 对每条：查唯一键，存在则更新 name/score/meta/strategy_id，否则 insert。
3. 删除同 `asof` 下不在集合内的旧行。

个股 `strategy_id="auction_strong"`；板块 `strategy_id="board"` 或 `None`（与规格「板块可空或 board」一致，推荐 `"board"`）。

- [ ] **Step 2: 尾盘**

在现有「按策略范围 delete 再 insert」处改为：对每个命中 upsert `(asof, strategy_id, code)`；跑完后删除**本 run 覆盖的 strategy_ids** 下未再命中的旧行（与当前 delete 范围一致：`use_all_closing` 则该 asof 全部策略，否则仅 `ids`）。

- [ ] **Step 3: 跑相关测**

```powershell
pytest tests/test_morning_brief.py tests/test_closing_pick.py tests/test_research_refine.py -q
```

（若文件名不同，按仓库实际测试文件名。）

- [ ] **Step 4: Commit**

```powershell
$msg = @"
feat(picks): 早盘尾盘候选 upsert 与策略字段
"@
git commit -m $msg
```

---

### Task 5: 前端日期选择 + asof 回看

**Files:**
- Modify: `apps/web/src/pages/Morning.tsx`
- Modify: `apps/web/src/pages/Closing.tsx`
- Modify: `apps/web/src/pages/sessionPick/shared.tsx`（`ResearchPickRow.strategy_id?`；表头可选「策略」列或在名称旁展示）

- [ ] **Step 1: 状态**

```tsx
const [asof, setAsof] = useState<string>(""); // YYYY-MM-DD；空=默认业务日
```

`load`：

```tsx
async function load(nextAsof?: string) {
  const q = nextAsof || asof;
  const url = q
    ? `/api/morning/latest?asof=${encodeURIComponent(q)}`
    : `/api/morning/latest`;
  // closing 同理；若 closing 要严格不回退可用 /history?asof=
  ...
  // 成功后若 data.asof 有值，setAsof(data.asof)
}
```

- [ ] **Step 2: Hero actions — 日期在「投研精选」左侧**

```tsx
<input
  type="date"
  className="..." // 与 SecondaryAction 高度协调
  value={asof || ""}
  disabled={busy}
  onChange={(e) => {
    const v = e.target.value;
    setAsof(v);
    void load(v);
  }}
  aria-label="选择回看日期"
/>
<SecondaryAction ... onPress={() => void runResearchRefine()}>
  投研精选
</SecondaryAction>
```

- [ ] **Step 3: refine / 其它操作带 asof**

`runResearchRefine` POST body 含 `asof: asof || data?.asof`；跑完 `load(asof)`。

空态：`emptyHint` 在无 picks 时用「该日暂无数据」或保留现有文案并在无 `data` 时提示。

- [ ] **Step 4: 策略展示**

`ResearchPickRow` 增加 `strategy_id?: string`。  
精选表增加一列「策略」：`auction_strong` → `竞价强势`，其它显示原 id（或后续接策略名 API，本任务不做额外接口）。

候选列表（强势个股 / 尾盘命中）若已有 strategy 字段则展示；早盘 stock 行显示「竞价强势」。

- [ ] **Step 5: Commit**

```powershell
$msg = @"
feat(web): 早尾盘按日回看与策略展示
"@
git commit -m $msg
```

---

### Task 6: 规格状态与总验证

- [ ] 规格头改为 `状态：已实现`
- [ ] 跑：

```powershell
pytest tests/test_research_source_label.py tests/test_research_table_image.py tests/test_research_refine.py tests/test_feishu_send_image.py -q
# 外加 morning/closing 相关测试文件
alembic upgrade head
```

- [ ] Commit：`docs: 投研按日回看规格标为已实现`

---

## Self-Review

1. **Spec coverage:** §1 文案 → Task 1；§2 落库 → Task 2–4；§3 UI → Task 5；验收 → Task 6。
2. **Placeholder scan:** 无 TBD；迁移 SQL 需按实际 DB（SQLite）微调时在 Task 2 实现中处理，不留空步骤。
3. **Type consistency:** `strategy_id` 贯穿 ORM / contract / list API / UI；`research_source_label` 仅用于展示。

---

## Execution

Plan complete — see handoff after file save.
