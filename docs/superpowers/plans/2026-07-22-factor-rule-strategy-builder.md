# 规则策略构建器 Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax. **不要自动 commit**（除非用户要求）。

**Goal:** 策略页可视化编辑因子比较/交叉规则，保存为 `kind: factor_rules` YAML，回测可执行。

**Architecture:** `desk_strategy.factor_rules` 求值器；`_yaml_on_bar` 按 `kind` 分发；前端 `StrategyRuleBuilder` 生成 YAML 并走现有保存 API。

**Tech Stack:** Python / FastAPI / YAML / React / 现有因子注册表

**Spec:** `docs/superpowers/specs/2026-07-22-factor-rule-strategy-builder-design.md`

**提交约定：** 仅用户要求时 commit。

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| Create: `packages/strategy/desk_strategy/factor_rules.py` | 解析条件、从 history 算因子、求值买卖信号 |
| Modify: `packages/strategy/desk_strategy/__init__.py` | `_yaml_on_bar` 分发 `factor_rules` |
| Create: `tests/test_factor_rules.py` | 比较 / 交叉 / AND/OR / 卖优先 |
| Create: `apps/web/src/pages/StrategyRuleBuilder.tsx` | 规则构建器 UI |
| Modify: `apps/web/src/App.tsx` | 路由 |
| Modify: `apps/web/src/pages/Strategies.tsx` | 入口「新建规则策略」；编辑时识别 kind |

---

### Task 1: factor_rules 求值器 + 单测

**Files:** Create `packages/strategy/desk_strategy/factor_rules.py`, `tests/test_factor_rules.py`

- [ ] **Step 1: 失败单测** — `eval_factor_rules(data, ctx) -> list[Signal]`

覆盖：
1. `RSI_14 < 30` → BUY（构造 history 使末 bar RSI 低）
2. `SMA_5` cross_up `SMA_20` → BUY
3. buy AND 两条件；sell OR；同 bar 买卖都真 → 仅 SELL
4. 未知因子 → 该条件假，不抛错

可用合成 OHLCV DataFrame 作 `ctx["history"]`，`ctx["row"]={"symbol":"UT.SH"}`。

- [ ] **Step 2: 实现**

```python
# 核心 API
def eval_factor_rules(data: dict, ctx: Any) -> list[Signal]:
    ...

def _resolve_operand(op: dict, cur: pd.Series, prev: pd.Series) -> float | None:
    # {factor: name} → 取该因子主输出列；{const: n} → float

def _eval_condition(cond, cur, prev) -> bool:
    # gt/gte/lt/lte/eq/cross_up/cross_down

def _enrich_history(history: pd.DataFrame, factor_names: list[str]) -> pd.DataFrame:
    # get_factor + apply_factor_specs；未知名跳过
```

交叉：`cross_up` = prev_left <= prev_right and left > right（None 则假）。

- [ ] **Step 3: pytest tests/test_factor_rules.py -v PASS**

---

### Task 2: 接入 `_yaml_on_bar`

**Files:** Modify `packages/strategy/desk_strategy/__init__.py`

- [ ] `kind == "factor_rules"`（或存在 buy/sell.conditions）→ `eval_factor_rules`
- [ ] 否则保留原 sma_fast/sma_slow 逻辑
- [ ] 可选：API 级 smoke（from_yaml + 手动 on_bar）放进 test_factor_rules

---

### Task 3: 前端规则构建器

**Files:** Create `StrategyRuleBuilder.tsx`；Modify `App.tsx`, `Strategies.tsx`

- [ ] 状态：id/name/version + buy/sell `{ combine, conditions[] }`
- [ ] 条件行：左因子 select（`GET /api/factors`，过滤 `category !== "ml"`）| op select | 右：模式「常数|因子」
- [ ] 序列化为 YAML（js-yaml 若项目已有；否则手写安全 dump 或 JSON→后端）
- [ ] 保存：`POST /api/strategies/from-yaml` 或现有保存接口（对齐 StrategyEdit）
- [ ] 路由：`/strategies/new/rules`、`/strategies/:strategyId/edit/rules`
- [ ] 列表：「新建规则策略」；编辑若 yaml 含 `kind: factor_rules` 跳规则页

检查项目是否已有 `js-yaml`；没有则用模板字符串拼 YAML（注意引号）。

---

### Task 4: 回归

- [ ] `pytest tests/test_factor_rules.py -v`
- [ ] 更新 `docs/TODO.md` 勾选该项；设计状态改为「实现中/已实现」

---

## Spec 覆盖

| 规格 | Task |
| --- | --- |
| 比较 + 交叉 | 1 |
| AND/OR 买卖 | 1 |
| 卖优先 | 1 |
| kind 分发 / 旧 YAML 兼容 | 2 |
| 策略页构建器 | 3 |
| 不接 ML | 3 过滤 ml |
