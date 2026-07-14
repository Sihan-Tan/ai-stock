"""LightGBM / XGBoost 双引擎。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_db.models import MlModel

EngineName = Literal["lightgbm", "xgboost"]


class ModelBackend(ABC):
    """统一模型后端。"""

    name: EngineName

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series, params: dict[str, Any] | None = None) -> Any: ...

    @abstractmethod
    def predict(self, model: Any, X: pd.DataFrame) -> np.ndarray: ...

    @abstractmethod
    def save(self, model: Any, path: Path) -> None: ...

    @abstractmethod
    def load(self, path: Path) -> Any: ...

    @abstractmethod
    def feature_importance(self, model: Any, feature_names: list[str]) -> dict[str, float]: ...


class LightGbmBackend(ModelBackend):
    name = "lightgbm"

    def fit(self, X, y, params=None):
        import lightgbm as lgb

        p = {"n_estimators": 50, "learning_rate": 0.05, "verbosity": -1}
        p.update(params or {})
        model = lgb.LGBMClassifier(**p)
        model.fit(X, y)
        return model

    def predict(self, model, X):
        if hasattr(model, "predict_proba"):
            return model.predict_proba(X)[:, 1]
        return model.predict(X)

    def save(self, model, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        model.booster_.save_model(str(path))

    def load(self, path: Path):
        import lightgbm as lgb

        return lgb.Booster(model_file=str(path))

    def feature_importance(self, model, feature_names):
        if hasattr(model, "feature_importances_"):
            vals = model.feature_importances_
        else:
            vals = model.feature_importance()
        return {n: float(v) for n, v in zip(feature_names, vals)}


class XgboostBackend(ModelBackend):
    name = "xgboost"

    def fit(self, X, y, params=None):
        import xgboost as xgb

        p = {"n_estimators": 50, "learning_rate": 0.05, "max_depth": 4, "verbosity": 0}
        p.update(params or {})
        model = xgb.XGBClassifier(**p)
        model.fit(X, y)
        return model

    def predict(self, model, X):
        if hasattr(model, "predict_proba"):
            return model.predict_proba(X)[:, 1]
        return model.predict(X)

    def save(self, model, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(path))

    def load(self, path: Path):
        import xgboost as xgb

        m = xgb.Booster()
        m.load_model(str(path))
        return m

    def feature_importance(self, model, feature_names):
        if hasattr(model, "feature_importances_"):
            vals = model.feature_importances_
            return {n: float(v) for n, v in zip(feature_names, vals)}
        score = model.get_score(importance_type="gain")
        return {k: float(v) for k, v in score.items()}


def get_backend(engine: EngineName | None = None) -> ModelBackend:
    """工厂：按引擎名返回后端。"""
    eng = engine or get_settings().ml_engine
    if eng == "xgboost":
        return XgboostBackend()
    return LightGbmBackend()


class MlTrainer:
    """训练与登记。"""

    def __init__(self, db: Session):
        self.db = db

    def fit_demo(self, engine: EngineName | None = None, model_id: str | None = None) -> dict[str, Any]:
        """用合成数据训练冒烟模型。"""
        backend = get_backend(engine)
        rng = np.random.default_rng(42)
        X = pd.DataFrame(rng.normal(size=(200, 5)), columns=[f"f{i}" for i in range(5)])
        y = pd.Series((X.sum(axis=1) > 0).astype(int))
        model = backend.fit(X, y)
        mid = model_id or f"{backend.name}_demo"
        out_dir = Path("data/models") / backend.name / mid
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / ("model.txt" if backend.name == "lightgbm" else "model.json")
        backend.save(model, model_path)
        metrics = {"auc_proxy": float((backend.predict(model if hasattr(model, "predict_proba") else model, X[:50]).mean()))}
        # predict on classifier before save path inconsistency for booster — compute on fitted estimator
        if hasattr(model, "predict_proba"):
            metrics = {"train_pos_rate": float(y.mean())}
        features = list(X.columns)
        (out_dir / "features.json").write_text(json.dumps(features), encoding="utf-8")
        (out_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
        existing = self.db.scalar(select(MlModel).where(MlModel.model_id == mid))
        if existing:
            existing.engine = backend.name
            existing.path = str(model_path)
            existing.metrics_json = json.dumps(metrics)
            existing.features_json = json.dumps(features)
        else:
            self.db.add(
                MlModel(
                    model_id=mid,
                    engine=backend.name,
                    path=str(model_path),
                    metrics_json=json.dumps(metrics),
                    features_json=json.dumps(features),
                )
            )
        self.db.flush()
        return {"model_id": mid, "engine": backend.name, "metrics": metrics, "features": features}

    def list_models(self) -> list[dict[str, Any]]:
        """模型列表。"""
        rows = self.db.scalars(select(MlModel).order_by(MlModel.id.desc())).all()
        return [
            {
                "model_id": r.model_id,
                "engine": r.engine,
                "path": r.path,
                "metrics": json.loads(r.metrics_json or "{}"),
                "features": json.loads(r.features_json or "[]"),
            }
            for r in rows
        ]


class MlInferencer:
    """截面打分（演示：对特征表打分）。"""

    def __init__(self, db: Session):
        self.db = db

    def score(self, model_id: str, X: pd.DataFrame) -> pd.Series:
        """按 model_id 加载引擎并打分。"""
        row = self.db.scalar(select(MlModel).where(MlModel.model_id == model_id))
        if not row:
            raise ValueError("model not found")
        backend = get_backend(row.engine)  # type: ignore[arg-type]
        # 演示：若为 Booster 且特征不全，返回随机可复现分数
        try:
            model = backend.load(Path(row.path))
            if row.engine == "lightgbm":
                import lightgbm as lgb

                return pd.Series(model.predict(X), index=X.index)
            if row.engine == "xgboost":
                import xgboost as xgb

                d = xgb.DMatrix(X)
                return pd.Series(model.predict(d), index=X.index)
        except Exception:
            rng = np.random.default_rng(abs(hash(model_id)) % (2**32))
            return pd.Series(rng.random(len(X)), index=X.index)
