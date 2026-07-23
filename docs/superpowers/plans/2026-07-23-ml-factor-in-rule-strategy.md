# 规则策略支持 ML 因子 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 已放入因子列表的 `ml:{model_id}` 可在 `factor_rules` 中与 TA 同等比较/交叉，回测与纸交易可跑；规则构建器下拉展示 `因子名（说明）` 且包含 ML。

**Architecture:** 扩展 `desk_strategy.factor_rules`：ML 列名=因子名；`FactorService`/`MlInferencer` 打分；`ctx["db"]` 注入；回测/Runner 对完整 history 预打分避免每 bar 重复推理。前端去掉 ML 过滤并改下拉文案。

**Tech Stack:** Python（factor_rules、FactorService、BacktestEngine、PaperStrategyRunner）、React（StrategyRuleBuilder）、pytest / vitest

**Spec:** `docs/superpowers/specs/2026-07-23-ml-factor-in-rule-strategy-design.md`

---

## 文件结构

| 文件 | 职责 |
| --- | --- |
| `packages/strategy/desk_strategy/factor_rules.py` | `_primary_output` 支持 `ml:`；`attach_ml_factor_columns`；enrich 拆分 TA/ML |
| `packages/strategy/desk_strategy/__init__.py` | YAML `on_bar` 注入 `db` |
| `packages/backtest/desk_backtest/__init__.py` | 回测前预打分 |
| `packages/broker/desk_broker/paper_runner.py` | Runner 评估前预打分 |
| `tests/test_factor_rules_ml.py` | ML 条件求值 / 缺 db / 预打分跳过 |
| `apps/web/src/pages/StrategyRuleBuilder.tsx` | 下拉含 ML + `名（说明）` |
| `apps/web/src/pages/StrategyRuleBuilder.test.ts` | 文案格式单测 |
| `docs/TODO.md` | 本期项勾选说明（实现完成后勾选；提醒两项后续） |

---

### Task 1: factor_rules 支持 ml: 列与 attach

**Files:**
- Modify: `packages/strategy/desk_strategy/factor_rules.py`
- Create: `tests/test_factor_rules_ml.py`

- [ ] **Step 1: 写失败单测（无 db 时 ml 条件为假；有列时可比较）**

```python
"""factor_rules + ml: 因子。"""

from __future__ import annotations

import pandas as pd

from desk_common.contracts import Side
from desk_strategy.factor_rules import (
    attach_ml_factor_columns,
    eval_factor_rules,
    _primary_output,
)


def _ohlcv(n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        c = 10.0 + i * 0.1
        rows.append(
            {
                "date": f"2024-01-{i + 1:02d}" if i < 28 else f"2024-02-{i - 27:02d}",
                "open": c,
                "high": c * 1.01,
                "low": c * 0.99,
                "close": c,
                "volume": 1_000_000.0,
            }
        )
    return pd.DataFrame(rows)


def test_primary_output_ml_is_factor_name():
    assert _primary_output("ml:demo") == "ml:demo"


def test_ml_compare_without_db_no_signal():
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "ml:demo"}, "right": {"const": 0.5}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": _ohlcv()})
    assert out == []


def test_ml_compare_with_precomputed_column_buys():
    hist = _ohlcv()
    hist["ml:demo"] = 0.2
    hist.loc[hist.index[-1], "ml:demo"] = 0.9
    data = {
        "kind": "factor_rules",
        "buy": {
            "combine": "all",
            "conditions": [
                {"op": "gt", "left": {"factor": "ml:demo"}, "right": {"const": 0.6}},
            ],
        },
        "sell": {"combine": "all", "conditions": []},
    }
    out = eval_factor_rules(data, {"row": {"symbol": "UT.SH"}, "history": hist})
    assert len(out) == 1
    assert out[0].side == Side.BUY


def test_attach_ml_skips_when_column_present():
    hist = _ohlcv()
    hist["ml:demo"] = 0.55
    out = attach_ml_factor_columns(hist, ["ml:demo"], db=None)
    assert list(out["ml:demo"]) == list(hist["ml:demo"])
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_factor_rules_ml.py -v`  
Expected: FAIL（`_primary_output` 对 ml 返回 None / `attach_ml_factor_columns` 未定义）

- [ ] **Step 3: 实现 factor_rules 改动**

在 `packages/strategy/desk_strategy/factor_rules.py`：

```python
_ML_PREFIX = "ml:"


def _primary_output(factor_name: str) -> str | None:
    """因子主输出列名；ml: 列名即因子名。"""
    if factor_name.startswith(_ML_PREFIX):
        return factor_name
    meta = get_factor(factor_name)
    ...


def attach_ml_factor_columns(
    history: pd.DataFrame,
    factor_names: list[str],
    db: Any = None,
) -> pd.DataFrame:
    """
    将缺失的 ml: 打分列写入 history（按 date 对齐）。

    列已存在或 db 为空则跳过对应名；未 as_factor / 解析失败则跳过不抛错。
    """
    if history is None or getattr(history, "empty", True):
        return history
    ml_names = [str(n) for n in factor_names if str(n).startswith(_ML_PREFIX)]
    missing = [n for n in ml_names if n not in history.columns]
    if not missing or db is None:
        return history

    from desk_factor import FactorService

    out = history.copy()
    svc = FactorService(db)
    for name in missing:
        try:
            row = svc._resolve_ml_model(name)
            packed = svc._ml_score_series(out, name, row)
        except Exception:  # noqa: BLE001
            continue
        points = (packed.get("outputs") or {}).get("ml_score") or []
        by_date = {str(p["date"])[:10]: p.get("v") for p in points}
        dates = out["date"].map(lambda d: str(d)[:10])
        out[name] = [by_date.get(d) for d in dates]
    return out


def enrich_history_with_factors(
    history: pd.DataFrame,
    factor_names: list[str],
    db: Any = None,
) -> pd.DataFrame:
    """TA apply_factor_specs + 缺失 ml: 列 attach。"""
    # 先 attach ml（可能 copy）
    out = attach_ml_factor_columns(history, factor_names, db)
    ta_names = [n for n in factor_names if not str(n).startswith(_ML_PREFIX)]
    # 其余保持原 enrich 逻辑，对 ta_names 调用 apply_factor_specs
    ...


def eval_factor_rules(data: dict[str, Any], ctx: Any) -> list[Signal]:
    ...
    db = ctx.get("db") if isinstance(ctx, dict) else None
    enriched = enrich_history_with_factors(history, names, db=db)
    ...
```

注意：`_resolve_operand` 已用 `_primary_output`；ml 列存在即可比较。交叉算子无需改。

- [ ] **Step 4: 跑测通过**

Run: `pytest tests/test_factor_rules_ml.py tests/test_factor_rules.py -v`  
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/strategy/desk_strategy/factor_rules.py tests/test_factor_rules_ml.py
git commit -m "feat(strategy): factor_rules 支持 ml: 打分列"
```

---

### Task 2: YAML on_bar 注入 db + 回测/Runner 预打分

**Files:**
- Modify: `packages/strategy/desk_strategy/__init__.py`
- Modify: `packages/backtest/desk_backtest/__init__.py`
- Modify: `packages/broker/desk_broker/paper_runner.py`
- Modify: `tests/test_factor_rules_ml.py`（可选：集成 attach + mock db 或真实 fit_demo）

- [ ] **Step 1: 改 from_yaml 的 on_bar 闭包，注入 db**

将 `_yaml_on_bar` 改为实例方法（或包装）：

```python
# from_yaml 内
on_bar=lambda ctx, d=data: self._yaml_on_bar(d, ctx),

def _yaml_on_bar(self, data: dict[str, Any], ctx: Any) -> list[Signal]:
    if isinstance(ctx, dict) and "db" not in ctx:
        ctx = {**ctx, "db": self.db}
    kind = str(data.get("kind") or "").strip().lower()
    if kind == "factor_rules" or (
        isinstance(data.get("buy"), dict) and "conditions" in (data.get("buy") or {})
    ):
        from desk_strategy.factor_rules import eval_factor_rules
        return eval_factor_rules(data, ctx)
    # ... 旧 sma 分支不变
```

删除原 `@staticmethod` 装饰（若有）；确认所有 `self._yaml_on_bar` 调用点仍正确。

- [ ] **Step 2: BacktestEngine.run 预打分**

在 `history_df = df.copy()` 之后、`cerebro.addstrategy` 之前：

```python
import yaml
from desk_strategy.factor_rules import attach_ml_factor_columns, collect_factor_names

body = getattr(reg.meta, "yaml_body", None) or ""
parsed = yaml.safe_load(body) if body else None
if isinstance(parsed, dict):
    history_df = attach_ml_factor_columns(
        history_df, collect_factor_names(parsed), self.db
    )
```

确认 `BacktestEngine` 有 `self.db`（与 `self.registry` 同源）。

- [ ] **Step 3: PaperStrategyRunner.run_once 预打分**

在 `history = df.copy()` 之后、`on_bar` 之前：

```python
import yaml
from desk_strategy.factor_rules import attach_ml_factor_columns, collect_factor_names

body = getattr(reg.meta, "yaml_body", None) or ""
parsed = yaml.safe_load(body) if body else None
if isinstance(parsed, dict):
    history = attach_ml_factor_columns(history, collect_factor_names(parsed), self.db)
signals = reg.on_bar({"row": row, "history": history, "db": self.db}) or []
```

- [ ] **Step 4: 集成单测（真实 as_factor 模型，可短）**

在 `tests/test_factor_rules_ml.py` 追加（复用 `test_ml_model_as_factor` 的 db fixture 模式）：

```python
def test_attach_ml_with_real_model(_db):
    """fit_demo + as_factor 后 attach 写出 ml: 列。"""
    from desk_ml import MlTrainer
    from desk_db import get_session_factory
    # seed 少量日线 → fit_demo → set_as_factor → attach_ml_factor_columns
    # assert name in columns and 至少一个非空分数
```

若 fit_demo 依赖行情种子，优先抄 `tests/test_ml_model_as_factor.py` / `tests/test_ml_train_symbols.py` 的灌数方式；过重则可 `@pytest.mark.skip` 并保证预计算列单测已覆盖主路径。

- [ ] **Step 5: 跑测**

Run: `pytest tests/test_factor_rules_ml.py tests/test_factor_rules.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packages/strategy/desk_strategy/__init__.py packages/backtest/desk_backtest/__init__.py packages/broker/desk_broker/paper_runner.py tests/test_factor_rules_ml.py
git commit -m "feat(strategy): 回测与纸交易预打分 ml 因子"
```

---

### Task 3: 前端下拉含 ML + 名（说明）

**Files:**
- Modify: `apps/web/src/pages/StrategyRuleBuilder.tsx`
- Modify: `apps/web/src/pages/StrategyRuleBuilder.test.ts`

- [ ] **Step 1: 导出纯函数并写单测**

在 `StrategyRuleBuilder.tsx`（或同文件顶部）增加：

```typescript
/**
 * 规则构建器因子下拉文案：因子名（说明）。
 * @param name 因子名
 * @param label 说明（API label）
 */
export function formatFactorOptionLabel(name: string, label: string): string {
  const tip = (label || "").trim();
  if (!tip || tip === name) return name;
  return `${name}（${tip}）`;
}
```

单测：

```typescript
import { formatFactorOptionLabel } from "../pages/StrategyRuleBuilder";

it("formats name with label in parentheses", () => {
  expect(formatFactorOptionLabel("RSI_14", "RSI")).toBe("RSI_14（RSI）");
  expect(formatFactorOptionLabel("ml:x", "x（lightgbm）")).toBe("ml:x（x（lightgbm））");
  expect(formatFactorOptionLabel("SMA_20", "SMA_20")).toBe("SMA_20");
});
```

- [ ] **Step 2: 改 factorOptions**

```typescript
const factorOptions = useMemo(
  () =>
    factors
      .filter((f) => f.enabled)
      .map((f) => ({
        value: f.name,
        label: formatFactorOptionLabel(f.name, f.label),
      })),
  [factors]
);
```

去掉 `category !== "ml"` 与 `!f.name.startsWith("ml:")`。

- [ ] **Step 3: vitest**

Run: `cd apps/web && npx vitest run src/pages/StrategyRuleBuilder.test.ts`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/StrategyRuleBuilder.tsx apps/web/src/pages/StrategyRuleBuilder.test.ts
git commit -m "feat(web): 规则策略因子下拉含 ML 并展示说明"
```

---

### Task 4: 文档收尾与提醒标记

**Files:**
- Modify: `docs/TODO.md`
- Modify: `docs/superpowers/specs/2026-07-23-ml-factor-in-rule-strategy-design.md`（状态改为已实现）

- [ ] **Step 1: 勾选本期待办**

将「规则策略支持 ML 因子」标为 `[x]`；保留下方「暂不做」两项为未勾选。

- [ ] **Step 2: Spec 状态**

`状态：已实现`

- [ ] **Step 3: Commit**

```bash
git add docs/TODO.md docs/superpowers/specs/2026-07-23-ml-factor-in-rule-strategy-design.md
git commit -m "docs: 标记 ML 因子规则策略已实现，保留后续待办"
```

- [ ] **Step 4: 完成后对用户提醒（实现会话必做）**

口头提醒：  
「规则策略 ML 因子已完成。按约定提醒：接下来可做 ① 因子页一键生成策略 ② 自动寻优阈值/仓位/持仓天数。」

---

## 自检

| Spec 要求 | 对应 Task |
| --- | --- |
| 仅 as_factor 的 ml 进规则 | Task 1（`_resolve_ml_model`）+ Task 3 下拉来自 `/api/factors` |
| 比较/交叉同等 | Task 1（列名 + 现有算子） |
| 预打分 | Task 2 |
| 下拉 `名（说明）` | Task 3 |
| 一键生成 / 寻优不做 | Task 4 保留 TODO + 提醒 |
