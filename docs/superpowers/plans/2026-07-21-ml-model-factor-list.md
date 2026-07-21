# 登记模型删除与放入因子列表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 已登记 ML 模型可删除；用户主动「放入因子列表」后出现在因子目录，勾选后对该股日线打分并画副图。

**Architecture:** `ml_models.as_factor` 持久化标记；`MlTrainer` 提供 delete / set_as_factor / list；`FactorService.list_factors` 合并 `ml:{model_id}` 伪因子；`compute_series` 对 ML 名走特征+`MlInferencer.score`；前端模型表增加放入/移出/删除。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、LightGBM/XGBoost、React、pytest

**Spec:** `docs/superpowers/specs/2026-07-21-ml-model-factor-list-design.md`

**提交约定：** 本仓库仅在用户明确要求时 `git commit`；计划中不强制每步提交。

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| Modify: `packages/db/desk_db/models.py` | `MlModel.as_factor` |
| Create: `alembic/versions/0008_ml_models_as_factor.py` | 迁移加列 |
| Modify: `packages/db/desk_db/__init__.py` | SQLite/PG 启动补列 |
| Modify: `packages/ml/desk_ml/__init__.py` | delete / set_as_factor；upsert 保留 as_factor；inferencer 失败抛错 |
| Modify: `packages/factor/desk_factor/__init__.py` | list 合并 ML；compute_series 打分分支 |
| Modify: `apps/api/app/routes/factor_ml.py` | DELETE / as-factor；factors 需 db |
| Create: `tests/test_ml_model_as_factor.py` | 删除、放入、目录、序列 |
| Modify: `apps/web/src/factors/FactorCatalog.tsx` | category `ml` 中文 |
| Modify: `apps/web/src/pages/Factors.tsx` | 模型表操作按钮 |

---

### Task 1: DB 字段 `as_factor`

**Files:**
- Modify: `packages/db/desk_db/models.py`
- Create: `alembic/versions/0008_ml_models_as_factor.py`
- Modify: `packages/db/desk_db/__init__.py`

- [ ] **Step 1: 模型加列**

在 `MlModel` 增加：

```python
as_factor: Mapped[bool] = mapped_column(default=False)
```

（与项目其它 bool 列风格一致；若用 Integer 则 0/1。）

- [ ] **Step 2: Alembic 0008**

```python
"""ml_models 增加 as_factor。"""

revision: str = "0008_ml_models_as_factor"
down_revision: Union[str, None] = "0007_lhb_daily_pct_chg"

def upgrade() -> None:
    op.add_column(
        "ml_models",
        sa.Column("as_factor", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

def downgrade() -> None:
    op.drop_column("ml_models", "as_factor")
```

- [ ] **Step 3: try_ensure_schema 补列**

仿 `_ensure_lhb_pct_chg_column`：

```python
def _ensure_ml_as_factor_column() -> None:
    engine = get_engine()
    dialect = engine.dialect.name
    if dialect == "sqlite":
        _ensure_sqlite_column("ml_models", "as_factor", "BOOLEAN DEFAULT 0")
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE ml_models ADD COLUMN IF NOT EXISTS as_factor BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
```

在 `try_ensure_schema` 中调用并 warning 吞异常。

---

### Task 2: MlTrainer 删除 / 放入 + Inferencer 硬失败

**Files:**
- Modify: `packages/ml/desk_ml/__init__.py`
- Create: `tests/test_ml_model_as_factor.py`（先写 delete/as_factor 部分）

- [ ] **Step 1: 写失败单测（delete / as_factor / list 字段）**

```python
"""登记模型删除与放入因子列表。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MARKET_SCHEDULER_ENABLED"] = "0"

from desk_common.settings import get_settings
from desk_db import Base, get_engine, get_session_factory, reset_engine
import desk_db.models  # noqa: F401
from desk_ml import MlTrainer


@pytest.fixture()
def _db(tmp_path, monkeypatch):
    get_settings.cache_clear()
    reset_engine()
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    yield
    reset_engine()
    get_settings.cache_clear()


def test_set_as_factor_and_delete(_db):
    db = get_session_factory()()
    try:
        out = MlTrainer(db).fit_demo(engine="lightgbm", model_id="ut_asf")
        db.commit()
        mid = out["model_id"]
        assert mid == "ut_asf"

        row = MlTrainer(db).set_as_factor(mid, True)
        db.commit()
        assert row["as_factor"] is True
        listed = MlTrainer(db).list_models()
        assert any(m["model_id"] == mid and m["as_factor"] for m in listed)

        MlTrainer(db).set_as_factor(mid, False)
        db.commit()
        assert not any(m["model_id"] == mid and m["as_factor"] for m in MlTrainer(db).list_models())

        path = Path(out["path"])
        assert path.exists()
        MlTrainer(db).delete_model(mid)
        db.commit()
        assert not path.exists() or not path.parent.exists()
        assert all(m["model_id"] != mid for m in MlTrainer(db).list_models())
    finally:
        db.close()


def test_delete_missing_raises(_db):
    db = get_session_factory()()
    try:
        with pytest.raises(ValueError, match="model not found"):
            MlTrainer(db).delete_model("no_such")
    finally:
        db.close()
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/test_ml_model_as_factor.py::test_set_as_factor_and_delete -v`  
Expected: FAIL（无 `set_as_factor` / `delete_model`）

- [ ] **Step 3: 实现方法**

`list_models` 每项增加 `"as_factor": bool(r.as_factor)`。

`_persist_model` upsert 时：**不覆盖**已有 `as_factor`（仅更新 engine/path/metrics/features）。

```python
def set_as_factor(self, model_id: str, as_factor: bool) -> dict[str, Any]:
    """标记是否出现在因子目录。"""
    row = self.db.scalar(select(MlModel).where(MlModel.model_id == model_id))
    if not row:
        raise ValueError("model not found")
    row.as_factor = bool(as_factor)
    self.db.flush()
    return {
        "model_id": row.model_id,
        "engine": row.engine,
        "as_factor": bool(row.as_factor),
        "path": row.path,
        "metrics": json.loads(row.metrics_json or "{}"),
        "features": json.loads(row.features_json or "[]"),
    }

def delete_model(self, model_id: str) -> None:
    """删除登记行与本地模型文件。"""
    import shutil

    row = self.db.scalar(select(MlModel).where(MlModel.model_id == model_id))
    if not row:
        raise ValueError("model not found")
    path = Path(row.path)
    self.db.delete(row)
    self.db.flush()
    # 删文件所在目录 data/models/{engine}/{model_id}
    target = path.parent if path.suffix else path
    if target.exists() and target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)
```

`MlInferencer.score`：加载/预测失败时 **raise**（去掉随机回退），便于因子序列 API 返回明确错误。若其它 demo 依赖随机回退，改为仅在显式 `fallback=True` 时回退；本功能路径不传 fallback。

- [ ] **Step 4: 跑测通过**

Run: `pytest tests/test_ml_model_as_factor.py -v`  
Expected: PASS（Task 2 相关用例）

---

### Task 3: FactorService 合并目录 + ML 序列

**Files:**
- Modify: `packages/factor/desk_factor/__init__.py`
- Modify: `tests/test_ml_model_as_factor.py`（追加用例）

- [ ] **Step 1: 追加单测**

```python
from datetime import date, timedelta
import pandas as pd
from desk_market import MarketService
from desk_factor import FactorService


def _seed_symbol(symbol: str, n: int = 200) -> None:
    end = date.today()
    rows = []
    for i in range(n):
        close = 100.0 + i * 0.3
        d = end - timedelta(days=n - 1 - i)
        rows.append({
            "date": d, "open": close - 0.2, "high": close + 0.5,
            "low": close - 0.5, "close": close, "volume": 1000.0,
            "amount": close * 1000, "open_hfq": close * 10, "high_hfq": close * 10 + 1,
            "low_hfq": close * 10 - 1, "close_hfq": close * 10, "volume_hfq": 1000.0,
        })
    db = get_session_factory()()
    try:
        MarketService(db).upsert_daily_bars(symbol, pd.DataFrame(rows))
        db.commit()
    finally:
        db.close()


def test_ml_factor_in_list_and_series(_db):
    _seed_symbol("600519.SH", 220)
    db = get_session_factory()()
    try:
        end = date.today()
        start = end - timedelta(days=60)
        # 用真实特征训练，避免 demo 的 f0..f4 与日线特征列不一致
        MlTrainer(db).fit_symbols(
            ["600519.SH"], start, end, engine="lightgbm", model_id="ut_ml_fac"
        )
        MlTrainer(db).set_as_factor("ut_ml_fac", True)
        db.commit()

        names = [f["name"] for f in FactorService(db).list_factors()]
        assert "ml:ut_ml_fac" in names

        out = FactorService(db).compute_series(
            "600519.SH", ["ml:ut_ml_fac"], start=start, end=end
        )
        pts = out["series"]["ml:ut_ml_fac"]["outputs"]["ml_score"]
        assert len(pts) == len(out["bars"])
        assert any(p["v"] is not None for p in pts)

        with pytest.raises(ValueError, match="not in factor list|as_factor|unknown"):
            FactorService(db).compute_series(
                "600519.SH", ["ml:nope"], start=start, end=end
            )
    finally:
        db.close()
```

说明：`fit_symbols` 特征与 `calc_features` 一致；勿用 `fit_demo` 测序列。

- [ ] **Step 2: 实现 FactorService**

`list_factors(self)`：若 `self.db` 有值，查询 `MlModel.as_factor == True`，追加：

```python
{
    "name": f"ml:{r.model_id}",
    "label": f"{r.model_id}（{r.engine}）",
    "category": "ml",
    "params": {"model_id": r.model_id, "engine": r.engine},
    "outputs": ["ml_score"],
    "plot": "panel",
    "default_enabled": False,
    "enabled": True,
    "talib": "",
}
```

`GET /api/factors` 改为注入 `db` 并 `FactorService(db).list_factors()`。

`compute_series_from_df` / `compute_series`：

- 解析 `ml:` 前缀名；未知或未 `as_factor` → `ValueError`。
- TA 名走现有逻辑；若只有 ML 名则 bars 仍从 ohlcv 建。
- ML 打分：

```python
from desk_strategy.ml_prob_engine import FEATURE_COLS, calc_features, preprocess_features
from desk_ml import MlInferencer

feats = calc_features(ohlcv)
feature_cols = json.loads(row.features_json) or FEATURE_COLS
X = preprocess_features(feats, feature_cols)[feature_cols]
scores = MlInferencer(self.db).score(model_id, X)
# 按 date 对齐；NaN 特征行 v=None
```

预热：`warmup_calendar_days` 对任意 `ml:` 名至少返回 `max(现有, 120)`（特征含 20 日波动等）。

合并 series：TA + ML 写入同一 `series` dict。

- [ ] **Step 3: 跑测**

Run: `pytest tests/test_ml_model_as_factor.py -v`  
Expected: PASS

---

### Task 4: API 路由

**Files:**
- Modify: `apps/api/app/routes/factor_ml.py`
- Modify: `tests/test_ml_model_as_factor.py`（API 用例）或扩 `tests/test_core.py`

- [ ] **Step 1: 路由**

```python
class AsFactorIn(BaseModel):
    as_factor: bool


@router.get("/factors")
def factors(db: Session = Depends(get_db)):
    return {"factors": FactorService(db).list_factors()}


@router.delete("/ml/models/{model_id}")
def delete_model(model_id: str, db: Session = Depends(get_db)):
    try:
        MlTrainer(db).delete_model(model_id)
        db.commit()
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True, "model_id": model_id}


@router.post("/ml/models/{model_id}/as-factor")
def set_as_factor(model_id: str, body: AsFactorIn, db: Session = Depends(get_db)):
    try:
        out = MlTrainer(db).set_as_factor(model_id, body.as_factor)
        db.commit()
        return out
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
```

`factor_series` 对 `ValueError` 继续 400（含未放入的 ml 名）。

- [ ] **Step 2: API 单测**

用 `TestClient`：`train-demo` 或 `fit_symbols` → POST as-factor → GET factors 含 `ml:...` → DELETE → GET models 无该项。

- [ ] **Step 3: 跑测**

Run: `pytest tests/test_ml_model_as_factor.py tests/test_factor_series.py tests/test_core.py -k "ml or factor" -v`  
Expected: PASS（相关用例）

---

### Task 5: 前端

**Files:**
- Modify: `apps/web/src/factors/FactorCatalog.tsx`
- Modify: `apps/web/src/pages/Factors.tsx`

- [ ] **Step 1: 目录分类文案**

`CATEGORY_LABELS` 增加：`ml: "机器学习"`。

- [ ] **Step 2: RegisteredModelsPanel 操作**

扩展 props：

```tsx
function RegisteredModelsPanel({
  models,
  onChanged,
  setLog,
}: {
  models: unknown[];
  onChanged: () => void;
  setLog: (s: string) => void;
})
```

每行操作：

- `as_factor` 为 false → 按钮「放入因子列表」→ `POST /api/ml/models/${id}/as-factor` body `{as_factor:true}`
- 为 true → 「移出因子列表」→ `{as_factor:false}`
- 「删除」→ `window.confirm` 后 `DELETE /api/ml/models/${id}`

成功后 `onChanged()`（父组件重新 `load` models + factors），`setLog` 写一句结果。

表头增加「状态」「操作」列；状态显示「已在因子列表」/「未放入」。

- [ ] **Step 3: 父组件接线**

`Factors` 的 `load` 已拉 factors + models；`RegisteredModelsPanel` 传入 `onChanged={load}`（或等价刷新）。放入成功后可用一句提示：「已放入，可到「因子图表」勾选」。

图表侧无需改 `FactorCharts`：`outputs: ["ml_score"]` + `plot: "panel"` 已支持单线副图。

---

### Task 6: 回归验证

- [ ] **Step 1: 后端**

Run: `pytest tests/test_ml_model_as_factor.py tests/test_ml_train_symbols.py tests/test_factor_series.py -v`  
Expected: 全部 PASS

- [ ] **Step 2: 手工（可选）**

模型训练 → 放入 → 因子图表目录见「机器学习」→ 勾选计算见副图 → 移出/删除。

---

## Spec 覆盖自检

| 规格项 | Task |
| --- | --- |
| 删除库+文件 | Task 2/4 |
| 放入/移出 as_factor | Task 2/4/5 |
| GET factors 合并 ml: | Task 3/4 |
| series 打分副图 | Task 3 |
| 未放入 400 | Task 3 |
| upsert 保留 as_factor | Task 2 |
| 打分失败可见 | Task 2 Inferencer |
| 不接回测 | 未做（正确） |

## Placeholder 扫描

无 TBD / 「类似 Task N」未展开项。
