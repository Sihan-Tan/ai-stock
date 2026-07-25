# 因子一键生成策略 + 完整阈值寻优 Implementation Plan

> **状态：已实现**（2026-07-25，见 `docs/superpowers/specs/2026-07-25-factor-rule-optimize-design.md`）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 因子页勾选因子一键跳转规则构建器并预填；对 `factor_rules` 网格寻优买卖阈值 / 仓位% / 最长持仓，写回 YAML；回测与纸交易读取 `params`。

**Architecture:** 前端 query 预填 + `POST /api/strategies/optimize-rules` 同步网格回测；`factor_rules` 顶层 `params.position_pct` / `params.max_hold_bars`；`BacktraderRunner` 改 sizer 与强制平仓；纸交易 Runner 对齐仓位%，持仓天数能通则做否则降级。

**Tech Stack:** FastAPI、YAML、`desk_backtest.BacktraderRunner`、`desk_strategy.factor_rules`、React、pytest、vitest

**Spec:** `docs/superpowers/specs/2026-07-25-factor-rule-optimize-design.md`

**约定：** 仅用户要求时 commit。Python docstring；前端新函数 JSDoc。

**写死的开放项：**

| 项 | 决定 |
| --- | --- |
| 振荡类白名单 | 因子名（忽略大小写）含：`RSI`、`CCI`、`WILLR`、`WR`、`STOCH`、`KDJ`、`MOM` |
| 缺省 `position_pct` | YAML **无** `params.position_pct` 时回测仍用 **95.0**；有则用该值 |
| 纸交易 `max_hold_bars` | 用持仓 `opened_at`/`created` 与日历交易日差；无开仓日字段则跳过强制平仓并在结果 `notes` 说明 |
| 寻优 HTTP | 同步；组合数 ≤200；前端 busy；建议客户端超时 ≥60s |

---

## File Structure

| 路径 | 职责 |
| --- | --- |
| Create: `packages/strategy/desk_strategy/rule_optimize.py` | 预填模板、改写阈值、网格枚举、选优 |
| Modify: `packages/strategy/desk_strategy/factor_rules.py` | 解析 `params`；`max_hold_bars` 强制卖；导出 `get_rule_params` |
| Modify: `packages/strategy/desk_strategy/__init__.py` | 导出；`_yaml_on_bar` 传入持仓 bar 计数（若需） |
| Modify: `packages/backtest/desk_backtest/__init__.py` | sizer 读 `position_pct`；策略持仓天数强制卖 |
| Modify: `packages/broker/desk_broker/paper_runner.py` | 下单比例读 `position_pct`；可选 max hold |
| Create: `apps/api/app/routes` 内 strategies 追加 optimize | `POST /api/strategies/optimize-rules` |
| Modify: `apps/web/src/pages/Factors.tsx` | 「生成规则策略」按钮 |
| Modify: `apps/web/src/pages/StrategyRuleBuilder.tsx` | query 预填 + 寻优弹层 |
| Create: `apps/web/src/pages/rulePrefill.ts`（或同文件导出） | 预填纯函数便于 vitest |
| Test: `tests/test_rule_optimize.py` | 网格、选优、上限、params |
| Test: `tests/test_factor_rules_params.py` 或并入 `test_factor_rules.py` | max_hold / params |
| Test: `apps/web/src/pages/rulePrefill.test.ts` | 预填映射 |

---

### Task 1: `params` 解析 + max_hold 强制卖

**Files:**
- Modify: `packages/strategy/desk_strategy/factor_rules.py`
- Test: `tests/test_factor_rules_params.py`

- [ ] **Step 1: 写失败单测**

```python
# tests/test_factor_rules_params.py
from desk_strategy.factor_rules import eval_factor_rules, get_rule_params

def test_get_rule_params_defaults():
    assert get_rule_params({}) == {"position_pct": None, "max_hold_bars": 0}
    assert get_rule_params({"params": {"position_pct": 50, "max_hold_bars": 5}})[
        "position_pct"
    ] == 50.0

def test_max_hold_forces_sell(history_df_with_close):
    """持仓已满 max_hold_bars 时即使无卖规则也出 SELL。"""
    data = {
        "kind": "factor_rules",
        "params": {"max_hold_bars": 2},
        "buy": {"combine": "all", "conditions": []},
        "sell": {"combine": "any", "conditions": []},
    }
    # ctx 需提供 bars_held=2（实现约定字段名 bars_held）
    sigs = eval_factor_rules(data, symbol="600519.SH", history=history_df_with_close, ctx={"bars_held": 2})
    assert any(s.side.name == "SELL" or s.side == Side.SELL for s in sigs)
```

（`history_df_with_close` 用现有 test_factor_rules fixture 风格自建短 DataFrame。）

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_factor_rules_params.py -q --tb=line`  
Expected: FAIL（`get_rule_params` 未定义）

- [ ] **Step 3: 实现 `get_rule_params` + max_hold 分支**

在 `factor_rules.py`：

```python
def get_rule_params(data: dict[str, Any]) -> dict[str, Any]:
    """读取 params.position_pct / max_hold_bars；缺省 position_pct=None，max_hold_bars=0。"""
    raw = data.get("params") if isinstance(data.get("params"), dict) else {}
    pos = _as_float(raw.get("position_pct"))
    hold = _as_float(raw.get("max_hold_bars"))
    max_hold = int(hold) if hold is not None and hold >= 0 and int(hold) == hold else 0
    return {"position_pct": pos, "max_hold_bars": max_hold}
```

在 `eval_factor_rules` 末尾（已有买卖信号合并之后）：若 `get_rule_params(data)["max_hold_bars"] > 0` 且 `int(ctx.get("bars_held") or 0) >= max_hold_bars`，追加 `Signal(..., side=SELL, reason="max_hold_bars")`（若尚无 SELL）。

- [ ] **Step 4: `_yaml_on_bar` / 回测策略注入 `bars_held`**

Modify `packages/backtest/desk_backtest/__init__.py` 的 `_SignalStrategy`：

- `__init__`：`self._bars_held = 0`
- `next`：若有仓则 `_bars_held += 1`，否则置 0；构造 `ctx` 时传入 `bars_held=self._bars_held`（查现有 `desk_on_bar` 调用处一并传入）

Modify `packages/strategy/desk_strategy/__init__.py` 中 factor_rules 的 on_bar 闭包：把 `ctx` 原样传给 `eval_factor_rules`。

- [ ] **Step 5: 跑通单测**

Run: `pytest tests/test_factor_rules_params.py tests/test_factor_rules.py -q --tb=line`  
Expected: PASS

- [ ] **Step 6: Commit**（仅用户要求时）

---

### Task 2: 回测 sizer 读 `position_pct`

**Files:**
- Modify: `packages/backtest/desk_backtest/__init__.py`
- Test: `tests/test_backtest_position_pct.py`

- [ ] **Step 1: 写失败单测**

用内存库 + 短日线 + 极简 always-buy YAML（可复用 closing 测试种子风格），两跑：

```python
def test_position_pct_50_vs_100_different_size(db):
    # params.position_pct=50 与 100 的首笔买入 qty 应近似一半关系（允许整手取整误差）
    ...
    assert qty50 * 2 <= qty100 + 100  # 宽松断言
```

若全链路过重：单测 `_ASharePercentSizer` 在 `percents=50` vs `100` 的 `_getsizing` mock 即可，并另测 Runner 把 YAML params 传到 `addsizer(..., percents=...)`（可用 monkeypatch 记录调用参数）。

- [ ] **Step 2: 实现**

在 `BacktraderRunner.run` 解析策略 YAML：

```python
from desk_strategy.factor_rules import get_rule_params
params = get_rule_params(parsed if isinstance(parsed, dict) else {})
percents = float(params["position_pct"]) if params["position_pct"] is not None else 95.0
percents = max(1.0, min(100.0, percents))
cerebro.addsizer(_ASharePercentSizer, percents=percents)
```

- [ ] **Step 3: 跑测 PASS**

- [ ] **Step 4: Commit**（仅用户要求时）

---

### Task 3: `rule_optimize` 核心（预填 + 网格 + 选优）

**Files:**
- Create: `packages/strategy/desk_strategy/rule_optimize.py`
- Modify: `packages/strategy/desk_strategy/__init__.py`（导出）
- Test: `tests/test_rule_optimize.py`

- [ ] **Step 1: 写失败单测**

```python
from desk_strategy.rule_optimize import (
    build_prefill_doc,
    apply_threshold_params,
    iter_optimize_grid,
    pick_best_result,
    count_grid,
)

def test_prefill_ml_and_rsi():
    doc = build_prefill_doc(["ml:demo", "RSI_14"])
    assert doc["kind"] == "factor_rules"
    assert doc["params"]["position_pct"] == 100
    assert doc["params"]["max_hold_bars"] == 0
    buy_ops = [c["op"] for c in doc["buy"]["conditions"]]
    assert "gt" in buy_ops and "lt" in buy_ops  # ml gt + rsi lt

def test_grid_cap():
    assert count_grid([0.5,0.6], [0.3,0.4], [50,100], [0,5,10,20]) == 2*2*2*4
    # 构造 >200 应在 validate_grid 抛 ValueError

def test_pick_best_prefers_return_then_dd():
    best = pick_best_result([
        {"metrics": {"total_return": 0.1, "max_drawdown": -0.2}, "key": "a"},
        {"metrics": {"total_return": 0.1, "max_drawdown": -0.1}, "key": "b"},
        {"metrics": {"total_return": 0.05, "max_drawdown": -0.01}, "key": "c"},
    ])
    assert best["key"] == "b"
```

- [ ] **Step 2: 实现 `rule_optimize.py` 要点**

```python
OSCILLATOR_TOKENS = ("RSI", "CCI", "WILLR", "WR", "STOCH", "KDJ", "MOM")
MAX_GRID = 200

def build_prefill_doc(factor_names: list[str]) -> dict: ...
def list_const_compare_slots(doc: dict, side: str) -> list[tuple[path...]]: ...
def apply_threshold_params(doc: dict, *, buy_v: float | None, sell_v: float | None,
                           position_pct: float, max_hold_bars: int) -> dict:
    """深拷贝；买侧所有「因子vs常数」比较的 const 同步为 buy_v（若 buy_v 非空）；卖侧同理。"""
def validate_grid(...) -> None:
    if count > MAX_GRID: raise ValueError(f"grid too large: {count} > {MAX_GRID}")
def optimize_rules_yaml(db, *, symbol, start, end, yaml_body: dict | str,
                        buy_grid, sell_grid, position_pcts, max_hold_bars_list) -> dict:
    """对每组调用 BacktraderRunner(persist=False)；返回 best + tried。"""
```

默认网格（API 未传时）：`buy_grid=[0.5,0.55,0.6,0.65,0.7]`，`sell_grid=[0.3,0.35,0.4,0.45,0.5]`，`position_pcts=[50,100]`，`max_hold_bars_list=[0,5,10,20]`。

若 `list_const_compare_slots` 买卖皆空 → `ValueError("无可优化阈值条件")`。

寻优时临时 `from_yaml` 或直接把改写后的 YAML 字符串交给 Runner：优先 **不落库**，扩展 Runner 接受 `yaml_body` 覆盖（或注册临时 strategy_id）。若现网 Runner 只认 `strategy_id`：在优化循环内 `StrategyRegistry.from_yaml` 写入临时 id（前缀 `opt_`）跑完删除，或给 `BacktraderRunner.run` 增加可选 `yaml_override: str | None`（**推荐后者**，避免脏库）。

- [ ] **Step 3: `BacktraderRunner.run` 支持 `yaml_override`**

```python
def run(self, req: BacktestRequest, *, persist: bool = True, yaml_override: str | None = None):
    ...
    if yaml_override:
        # 用临时 on_bar：StrategyRegistry._yaml_on_bar_from_text(yaml_override) 或 inline safe_load + factor_rules
```

最小改动：若 `yaml_override`，解析后 `on_bar = registry._make_factor_rules_on_bar(parsed)`（抽现有分支为方法）。

- [ ] **Step 4: 跑通 `tests/test_rule_optimize.py`**

- [ ] **Step 5: Commit**（仅用户要求时）

---

### Task 4: API `POST /api/strategies/optimize-rules`

**Files:**
- Modify: `apps/api/app/routes/strategies.py`
- Test: `tests/test_optimize_rules_api.py`（TestClient + mock optimize 或短数据）

- [ ] **Step 1: 请求体与路由**

```python
class OptimizeRulesIn(BaseModel):
    symbol: str
    start: date
    end: date
    yaml_body: dict | str
    buy_grid: list[float] | None = None
    sell_grid: list[float] | None = None
    position_pcts: list[float] | None = None
    max_hold_bars_list: list[int] | None = None

@router.post("/optimize-rules")
def optimize_rules(body: OptimizeRulesIn, db: Session = Depends(get_db)):
    try:
        return optimize_rules_yaml(db, **body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
```

- [ ] **Step 2: API 单测** — 无常数条件 → 400；超大网格 → 400

- [ ] **Step 3: Commit**（仅用户要求时）

---

### Task 5: 前端预填 + 因子页按钮

**Files:**
- Create: `apps/web/src/pages/rulePrefill.ts`
- Create: `apps/web/src/pages/rulePrefill.test.ts`
- Modify: `apps/web/src/pages/Factors.tsx`
- Modify: `apps/web/src/pages/StrategyRuleBuilder.tsx`

- [ ] **Step 1: vitest 预填**

```ts
import { buildPrefillRuleDoc } from "./rulePrefill";

test("ml and rsi defaults", () => {
  const doc = buildPrefillRuleDoc(["ml:x", "RSI_14"]);
  expect(doc.buy.combine).toBe("all");
  expect(doc.params.position_pct).toBe(100);
});
```

映射逻辑与 Python `build_prefill_doc` **保持一致**（白名单 token 相同）。

- [ ] **Step 2: Factors「生成规则策略」**

```tsx
<Button
  isDisabled={selected.size === 0}
  onPress={() => {
    const q = encodeURIComponent([...selected].join(","));
    navigate(`/strategies/new/rules?from=factors&factors=${q}`);
  }}
>
  生成规则策略
</Button>
```

放在因子图表 Tab 操作区（有勾选时可见）。

- [ ] **Step 3: StrategyRuleBuilder 读 query**

```tsx
const [sp] = useSearchParams();
useEffect(() => {
  if (sp.get("from") !== "factors") return;
  const names = (sp.get("factors") || "").split(",").map(s => s.trim()).filter(Boolean);
  if (!names.length) return;
  setDoc(buildPrefillRuleDoc(names));
}, [sp, factorsLoaded]);
```

注意：等 `factorOptions` 加载后再 set，避免被空初始 doc 覆盖。

- [ ] **Step 4: 跑 vitest**

Run: `cd apps/web && npx vitest run src/pages/rulePrefill.test.ts`

- [ ] **Step 5: Commit**（仅用户要求时）

---

### Task 6: 前端寻优弹层

**Files:**
- Modify: `apps/web/src/pages/StrategyRuleBuilder.tsx`

- [ ] **Step 1: UI**

工具栏按钮「阈值寻优」→ 简单面板：标的输入（默认空）、`DateRangePresetSelect`、提交。

```ts
const res = await api<OptimizeResult>("/api/strategies/optimize-rules", {
  method: "POST",
  body: JSON.stringify({
    symbol,
    start: dateRange.start,
    end: dateRange.end,
    yaml_body: doc, // 或 dump 后的对象
  }),
});
setDoc(parseFactorRulesYaml(dump or res.best.yaml_body));
setLog(`寻优完成 return=${res.best.metrics.total_return}`);
```

busy / 错误展示 HTTP 400 文案。

- [ ] **Step 2: 手工验收清单**

1. 因子页勾选 `RSI_14` + 一 `ml:` → 生成 → 见预填  
2. 寻优小区间（有日线的标的）→ 常数与 params 更新  
3. 保存策略后回测，`position_pct=50` 与满仓差异可感（或看报告）

- [ ] **Step 3: Commit**（仅用户要求时）

---

### Task 7: 纸交易对齐（尽力）+ 文档

**Files:**
- Modify: `packages/broker/desk_broker/paper_runner.py`（读策略 yaml params 调仓位%；max_hold 有开仓日则强制卖）
- Modify: `docs/TODO.md`（勾选两项）
- Modify: `docs/superpowers/specs/2026-07-25-factor-rule-optimize-design.md` → `状态：已实现`

- [x] **Step 1: Runner** — 解析当前策略 YAML `get_rule_params`；下单 qty 按权益 × position_pct/100（仍受风控）；无开仓日则 `notes`  
- [x] **Step 2: 更新 TODO / spec 状态**  
- [ ] **Step 3: Commit**（仅用户要求时）

---

## Spec coverage（自检）

| 规格项 | Task |
| --- | --- |
| 一键生成跳转与预填 | 5 |
| ML/振荡/TA 默认条件 | 3 + 5 |
| 默认 params 100 / 0 | 3 |
| 寻优 API 与网格上限 200 | 3 + 4 |
| 同侧常数同步替换 | 3 |
| 目标 return + dd 平局 | 3 |
| position_pct sizer | 2 |
| max_hold 强制卖 | 1 |
| UI 寻优 | 6 |
| 纸交易尽力 | 7 |
| TODO 勾选 | 7 |

**Placeholder 扫描：** 无 TBD；临时策略 vs `yaml_override` 已在 Task 3 推荐写死为 override。

---

## 执行方式

Plan complete and saved to `docs/superpowers/plans/2026-07-25-factor-rule-optimize.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每 Task 新开子代理，任务间复查  
2. **Inline Execution** — 本会话按 executing-plans 连续做完，关键检查点停一下  

你选 **1** 还是 **2**？
