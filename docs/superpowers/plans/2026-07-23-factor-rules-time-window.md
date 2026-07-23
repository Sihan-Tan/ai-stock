# 规则条件跨日窗口（sequence / within）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `factor_rules` 增加 `combine: sequence`（有序间隔）与 `combine: within`（近 N 日均曾成立，允许同日），并在规则构建器可编辑 `within_bars`。

**Architecture:** 在 `factor_rules` 中抽取「任意 bar 上求单条条件」；`_side_triggered` 按 combine 分发 all/any/sequence/within，sequence/within 扫描已 enrich 的 history。前端扩展 `RuleSide.combine` 与 dump/parse。现有 `all`/`any` 行为保持不变。

**Tech Stack:** Python（`desk_strategy.factor_rules`、pytest）、React（`StrategyRuleBuilder`、vitest）

**Spec:** `docs/superpowers/specs/2026-07-23-factor-rules-time-window-design.md`

---

## File map

| 文件 | 职责 |
| --- | --- |
| `packages/strategy/desk_strategy/factor_rules.py` | `eval_condition_at`、`_parse_within_bars`、sequence/within 侧触发；改 `_side_triggered` / `eval_factor_rules` |
| `tests/test_factor_rules.py` | 跨日 combine 单测 + all 回归 |
| `apps/web/src/pages/StrategyRuleBuilder.tsx` | 类型、dump/parse、组合下拉、窗口输入 |
| `apps/web/src/pages/StrategyRuleBuilder.test.ts` | dump/parse sequence + within_bars |

---

### Task 1: 后端 — 失败单测（sequence / within）

**Files:**
- Modify: `tests/test_factor_rules.py`
- Modify: `packages/strategy/desk_strategy/factor_rules.py`（Task 2 实现）

- [ ] **Step 1: 追加单测**（依赖预置列，避免 TA 噪声）

在 `tests/test_factor_rules.py` 末尾追加：

```python
def test_sequence_same_day_two_steps():
    """sequence 允许同日两步；末步在今日（CLOSE 同时 >5 且 <20）。"""
    hist = _ohlcv([10.0] * 30)
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 5}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 20}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY


def test_sequence_gap_within_window():
    """条件1 在 T-3 真、条件2 在今日真，within_bars=5 → 买。"""
    hist = _ohlcv([10.0] * 30)
    # T-3: close=12（>11），其余日 close=10（不满足 >11）；今日 close=9（<9.5）
    hist.loc[hist.index[:-1], "close"] = 10.0
    hist.loc[hist.index[-4], "close"] = 12.0
    hist.loc[hist.index[-1], "close"] = 9.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY


def test_sequence_gap_exceeds_window_no_signal():
    """间隔超过 within_bars → 不触发。"""
    hist = _ohlcv([10.0] * 30)
    hist.loc[hist.index[:-1], "close"] = 10.0
    hist.loc[hist.index[-10], "close"] = 12.0  # 距今 9 根
    hist.loc[hist.index[-1], "close"] = 9.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    assert eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist}) == []


def test_sequence_last_step_not_today_no_signal():
    """末条件仅在昨日真、今日假 → 不触发。"""
    hist = _ohlcv([10.0] * 30)
    hist["close"] = 10.0
    hist.loc[hist.index[-2], "close"] = 9.0  # 昨日 < 9.5
    hist.loc[hist.index[-5], "close"] = 12.0
    # 今日 close=10：不满足 lt 9.5
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "sequence",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    assert eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist}) == []


def test_within_unordered_and_same_day():
    """within：两条件不同日或同日均可；无序。"""
    hist = _ohlcv([10.0] * 30)
    hist["close"] = 10.0
    hist.loc[hist.index[-3], "close"] = 12.0  # >11
    hist.loc[hist.index[-1], "close"] = 9.0  # <9.5；同窗
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "within",
            "within_bars": 5,
            "conditions": [
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 9.5}},
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1 and out[0].side == Side.BUY

    # 同日：今日 close 同时满足两阈值不可能，改两条件皆可用今日：gt 5 与 lt 20
    hist2 = _ohlcv([10.0] * 30)
    data2 = {
        "kind": "factor_rules",
        "buy": {
            "combine": "within",
            "within_bars": 5,
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 5}},
                {"op": "lt", "left": {"factor": "CLOSE"}, "right": {"const": 20}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out2 = eval_factor_rules(data2, {"row": {"symbol": "UT.SH"}, "history": hist2})
    assert len(out2) == 1 and out2[0].side == Side.BUY


def test_combine_all_unchanged_regression():
    """all 仍只看当日：昨日曾 >11、今日 =10 不触发 gt 11。"""
    hist = _ohlcv([10.0] * 30)
    hist["close"] = 10.0
    hist.loc[hist.index[-2], "close"] = 12.0
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "CLOSE"}, "right": {"const": 11}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    assert eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist}) == []
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_factor_rules.py::test_sequence_gap_within_window tests/test_factor_rules.py::test_within_unordered_and_same_day -v`

Expected: FAIL（`combine: sequence`/`within` 被当作 `all` 处理或未识别）

---

### Task 2: 后端 — 实现 sequence / within

**Files:**
- Modify: `packages/strategy/desk_strategy/factor_rules.py`

- [ ] **Step 1: 增加常量与解析**

在 `_DEFAULT_NEAR_PCT` 旁增加：

```python
_DEFAULT_WITHIN_BARS = 5


def _parse_within_bars(block: dict[str, Any]) -> int:
    """侧级 within_bars；非法/缺失 → 默认 5。"""
    raw = block.get("within_bars")
    if raw is None or raw == "":
        return _DEFAULT_WITHIN_BARS
    v = _as_float(raw)
    if v is None or v < 0 or int(v) != v:
        return _DEFAULT_WITHIN_BARS
    return int(v)
```

- [ ] **Step 2: `eval_condition_at`**

```python
def eval_condition_at(cond: dict[str, Any], enriched: pd.DataFrame, i: int) -> bool:
    """在 bar 下标 i 上求单条条件；交叉需要 i>=1。"""
    if i < 0 or i >= len(enriched):
        return False
    op = str(cond.get("op") or "").strip().lower()
    if op in CROSS_OPS and i < 1:
        return False
    cur = enriched.iloc[i]
    prev = enriched.iloc[i - 1] if i >= 1 else cur
    return eval_condition(cond, cur, prev)
```

- [ ] **Step 3: sequence / within 辅助函数**

```python
def _sequence_triggered(
    conditions: list[Any], enriched: pd.DataFrame, today_i: int, within_bars: int
) -> bool:
    """有序间隔：末步须在 today_i；相邻下标差 ∈ [0, within_bars]。"""
    if within_bars < 0 or not conditions:
        return False
    conds = [c for c in conditions if isinstance(c, dict)]
    if not conds:
        return False
    if not eval_condition_at(conds[-1], enriched, today_i):
        return False
    cursor = today_i
    for j in range(len(conds) - 2, -1, -1):
        lo = max(0, cursor - within_bars)
        found: int | None = None
        for i in range(cursor, lo - 1, -1):
            if eval_condition_at(conds[j], enriched, i):
                found = i
                break
        if found is None:
            return False
        cursor = found
    return True


def _within_triggered(
    conditions: list[Any], enriched: pd.DataFrame, today_i: int, within_bars: int
) -> bool:
    """近窗内每条至少一日为真；允许同日；无序。"""
    if within_bars < 0 or not conditions:
        return False
    lo = max(0, today_i - within_bars)
    for cond in conditions:
        if not isinstance(cond, dict):
            return False
        hit = False
        for i in range(lo, today_i + 1):
            if eval_condition_at(cond, enriched, i):
                hit = True
                break
        if not hit:
            return False
    return True
```

- [ ] **Step 4: 改写 `_side_triggered` 与 `eval_factor_rules`**

将 `_side_triggered` 签名改为接收完整帧：

```python
def _side_triggered(block: Any, enriched: pd.DataFrame, today_i: int) -> bool:
    if not isinstance(block, dict):
        return False
    conditions = block.get("conditions") or []
    if not conditions:
        return False
    combine = str(block.get("combine") or "all").strip().lower()
    if combine == "sequence":
        return _sequence_triggered(conditions, enriched, today_i, _parse_within_bars(block))
    if combine == "within":
        return _within_triggered(conditions, enriched, today_i, _parse_within_bars(block))
    cur = enriched.iloc[today_i]
    prev = enriched.iloc[today_i - 1] if today_i >= 1 else cur
    results: list[bool] = []
    for cond in conditions:
        if isinstance(cond, dict):
            results.append(eval_condition(cond, cur, prev))
        else:
            results.append(False)
    if not results:
        return False
    if combine == "any":
        return any(results)
    return all(results)
```

`eval_factor_rules` 内改为：

```python
    today_i = len(enriched) - 1
    sell_on = _side_triggered(data.get("sell"), enriched, today_i)
    buy_on = _side_triggered(data.get("buy"), enriched, today_i)
```

- [ ] **Step 5: 跑通全部 factor_rules 单测**

Run: `pytest tests/test_factor_rules.py -v`

Expected: PASS（含 Task 1 新测与原有测）

- [ ] **Step 6: Commit**（若用户要求提交；否则跳过）

```bash
git add packages/strategy/desk_strategy/factor_rules.py tests/test_factor_rules.py
git commit -m "feat(strategy): factor_rules 支持 sequence/within 跨日组合"
```

---

### Task 3: 前端 — dump/parse + UI

**Files:**
- Modify: `apps/web/src/pages/StrategyRuleBuilder.tsx`
- Modify: `apps/web/src/pages/StrategyRuleBuilder.test.ts`

- [ ] **Step 1: 扩展类型**

```typescript
type RuleCombine = "all" | "any" | "sequence" | "within";

type RuleSide = {
  combine: RuleCombine;
  /** sequence/within：间隔或窗口（交易日），默认 5 */
  within_bars?: number;
  conditions: RuleCondition[];
};
```

- [ ] **Step 2: dumpSide**

```typescript
    const combine =
      side.combine === "any"
        ? "any"
        : side.combine === "sequence"
          ? "sequence"
          : side.combine === "within"
            ? "within"
            : "all";
    lines.push(`  combine: ${combine}`);
    if (combine === "sequence" || combine === "within") {
      const n = Number.isFinite(side.within_bars) ? Number(side.within_bars) : 5;
      lines.push(`  within_bars: ${Math.max(0, Math.floor(n))}`);
    }
```

- [ ] **Step 3: parseSide**

```typescript
    const combineM = block.match(/combine:\s*(all|any|sequence|within)/);
    if (combineM) side.combine = combineM[1] as RuleCombine;
    const wbM = block.match(/within_bars:\s*(\d+)/);
    if (wbM) side.within_bars = Number(wbM[1]);
    else if (side.combine === "sequence" || side.combine === "within") side.within_bars = 5;
```

- [ ] **Step 4: UI（SideEditor 组合下拉旁）**

- `select` 增加选项：`有序间隔` → `sequence`，`近N日均曾成立` → `within`。
- `onChange`：写入对应 combine；切到 sequence/within 且无 `within_bars` 时设为 5。
- 当 `combine === "sequence" || combine === "within"` 时渲染数字输入：

```tsx
<label className="text-xs text-[var(--desk-mist)]">
  {side.combine === "sequence" ? "相邻间隔≤（交易日）" : "近窗（交易日）"}
  <input
    type="number"
    min={0}
    className={controlClass + " ml-2 w-20"}
    value={side.within_bars ?? 5}
    onChange={(e) =>
      onChange({
        ...side,
        within_bars: Math.max(0, Math.floor(Number(e.target.value) || 0)),
      })
    }
  />
</label>
```

（找到现有 `value={side.combine}` 的 select，按上扩展；勿改动无关布局。）

- [ ] **Step 5: vitest**

在 `StrategyRuleBuilder.test.ts` 追加：

```typescript
  it("dumps and parses sequence with within_bars", () => {
    const yaml = dumpFactorRulesYaml({
      id: "rule_seq",
      name: "跨日",
      version: "v1.0",
      kind: "factor_rules",
      buy: {
        combine: "sequence",
        within_bars: 5,
        conditions: [
          {
            op: "cross_up",
            left: { kind: "factor", factor: "SMA_5" },
            right: { kind: "factor", factor: "SMA_20" },
          },
          {
            op: "near_pct",
            left: { kind: "factor", factor: "CLOSE" },
            right: { kind: "factor", factor: "SMA_20" },
            pct: 3,
          },
        ],
      },
      sell: { combine: "within", within_bars: 10, conditions: [] },
    });
    expect(yaml).toContain("combine: sequence");
    expect(yaml).toContain("within_bars: 5");
    expect(yaml).toContain("combine: within");
    expect(yaml).toContain("within_bars: 10");
    const parsed = parseFactorRulesYaml(yaml);
    expect(parsed?.buy.combine).toBe("sequence");
    expect(parsed?.buy.within_bars).toBe(5);
    expect(parsed?.sell.combine).toBe("within");
    expect(parsed?.sell.within_bars).toBe(10);
  });
```

Run: `cd apps/web && npx vitest run src/pages/StrategyRuleBuilder.test.ts`

Expected: PASS

- [ ] **Step 6: 更新设计文档状态**

将 `docs/superpowers/specs/2026-07-23-factor-rules-time-window-design.md` 的 **状态** 改为 `已实现`。

- [ ] **Step 7: Commit**（若用户要求提交；否则跳过）

```bash
git add apps/web/src/pages/StrategyRuleBuilder.tsx apps/web/src/pages/StrategyRuleBuilder.test.ts docs/superpowers/specs/2026-07-23-factor-rules-time-window-design.md docs/superpowers/plans/2026-07-23-factor-rules-time-window.md
git commit -m "feat(web): 规则构建器支持 sequence/within 跨日组合"
```

---

## Spec coverage（自检）

| Spec 项 | Task |
| --- | --- |
| `sequence` 语义与同日间隔 0 | Task 1–2 |
| `within` 无序、允许同日 | Task 1–2 |
| 默认 `within_bars=5` | Task 2 `_parse_within_bars`；Task 3 dump/parse |
| 末步须在当日 | `test_sequence_last_step_not_today_no_signal` |
| `all`/`any` 不变 | `test_combine_all_unchanged_regression` + 原测 |
| 买卖两侧 | 同一 `_side_triggered` |
| 前端 dump/parse/UI | Task 3 |
| 不做状态机/条件级窗口 | 未列入任务 |

## Placeholder scan

无 TBD /「类似 Task N」占位。
