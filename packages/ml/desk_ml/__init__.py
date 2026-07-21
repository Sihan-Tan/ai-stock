"""LightGBM / XGBoost 双引擎。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.settings import get_settings
from desk_common.symbols import normalize_symbol
from desk_db.models import MlModel

EngineName = Literal["lightgbm", "xgboost"]

# 训练日线向前多取的日历日（覆盖特征预热）
_TRAIN_WARMUP_CALENDAR_DAYS = 180
_MIN_BARS_PER_SYMBOL = 60
_MIN_CLEAN_ROWS = 30


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

    def _persist_model(
        self,
        *,
        backend: ModelBackend,
        model: Any,
        model_id: str,
        metrics: dict[str, Any],
        features: list[str],
    ) -> dict[str, Any]:
        """落盘模型文件并 upsert ml_models 行。"""
        out_dir = Path("data/models") / backend.name / model_id
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / ("model.txt" if backend.name == "lightgbm" else "model.json")
        backend.save(model, model_path)
        (out_dir / "features.json").write_text(json.dumps(features), encoding="utf-8")
        (out_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
        existing = self.db.scalar(select(MlModel).where(MlModel.model_id == model_id))
        if existing:
            existing.engine = backend.name
            existing.path = str(model_path)
            existing.metrics_json = json.dumps(metrics)
            existing.features_json = json.dumps(features)
        else:
            self.db.add(
                MlModel(
                    model_id=model_id,
                    engine=backend.name,
                    path=str(model_path),
                    metrics_json=json.dumps(metrics),
                    features_json=json.dumps(features),
                )
            )
        self.db.flush()
        return {
            "model_id": model_id,
            "engine": backend.name,
            "metrics": metrics,
            "features": features,
            "path": str(model_path),
        }

    def fit_demo(self, engine: EngineName | None = None, model_id: str | None = None) -> dict[str, Any]:
        """用合成数据训练冒烟模型。"""
        backend = get_backend(engine)
        rng = np.random.default_rng(42)
        X = pd.DataFrame(rng.normal(size=(200, 5)), columns=[f"f{i}" for i in range(5)])
        y = pd.Series((X.sum(axis=1) > 0).astype(int))
        model = backend.fit(X, y)
        mid = model_id or f"{backend.name}_demo"
        metrics = {"train_pos_rate": float(y.mean()), "n_samples": int(len(y))}
        features = list(X.columns)
        return self._persist_model(
            backend=backend, model=model, model_id=mid, metrics=metrics, features=features
        )

    def build_symbol_dataset(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> tuple[pd.DataFrame, pd.Series, list[str], list[dict[str, str]]]:
        """
        多股日线拼成训练矩阵。

        @returns: X, y, used_symbols, skipped[{symbol, reason}]
        @raises ValueError: 无可用样本
        """
        from desk_market import MarketService
        from desk_strategy.ml_prob_engine import (
            FEATURE_COLS,
            calc_features,
            make_labels,
            preprocess_features,
        )

        market = MarketService(self.db)
        load_start = start - timedelta(days=_TRAIN_WARMUP_CALENDAR_DAYS)
        frames: list[pd.DataFrame] = []
        skipped: list[dict[str, str]] = []
        used: list[str] = []

        for raw in symbols:
            sym = normalize_symbol(str(raw or ""))
            if not sym:
                continue
            df = market.load_daily_df(sym, load_start, end)
            if df.empty or len(df) < _MIN_BARS_PER_SYMBOL:
                skipped.append({"symbol": sym, "reason": "insufficient_bars"})
                continue
            feat = calc_features(df)
            feat["label"] = make_labels(feat["close"])
            date_col = pd.to_datetime(feat["date"]).dt.date
            visible = feat.loc[(date_col >= start) & (date_col <= end)].copy()
            cols = [c for c in FEATURE_COLS if c in visible.columns]
            clean = visible.dropna(subset=cols + ["label"])
            if len(clean) < _MIN_CLEAN_ROWS:
                skipped.append({"symbol": sym, "reason": "insufficient_clean"})
                continue
            clean["symbol"] = sym
            frames.append(clean)
            used.append(sym)

        if not frames:
            raise ValueError("无可用训练样本（请确认标的有足够本地日线）")

        all_df = pd.concat(frames, ignore_index=True)
        cols = [c for c in FEATURE_COLS if c in all_df.columns]
        all_df = preprocess_features(all_df, cols)
        X = all_df[cols]
        y = all_df["label"].astype(int)
        return X, y, used, skipped

    def fit_symbols(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        engine: EngineName | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        用多股本地日线特征训练二分类模型（标签=次日上涨）。

        @raises ValueError: 无样本或参数非法
        """
        if start > end:
            raise ValueError("start 不能晚于 end")
        if not symbols:
            raise ValueError("symbols required")

        backend = get_backend(engine)
        X, y, used, skipped = self.build_symbol_dataset(symbols, start, end)
        model = backend.fit(X, y)
        pred = backend.predict(model, X)
        # 概率阈值 0.5 近似准确率
        y_hat = (np.asarray(pred) >= 0.5).astype(int)
        acc = float((y_hat == y.to_numpy()).mean()) if len(y) else 0.0
        mid = model_id or f"{backend.name}_symbols"
        metrics = {
            "n_samples": int(len(y)),
            "n_symbols": len(used),
            "train_pos_rate": float(y.mean()),
            "train_accuracy": acc,
        }
        result = self._persist_model(
            backend=backend,
            model=model,
            model_id=mid,
            metrics=metrics,
            features=list(X.columns),
        )
        result["symbols_used"] = used
        result["skipped"] = skipped
        result["start"] = start.isoformat()
        result["end"] = end.isoformat()
        return result

    def compare_engines_on_symbols(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> dict[str, Any]:
        """同股票池、同区间对比 LightGBM 与 XGBoost。"""
        a = self.fit_symbols(
            symbols, start, end, engine="lightgbm", model_id="cmp_lgb_symbols"
        )
        b = self.fit_symbols(
            symbols, start, end, engine="xgboost", model_id="cmp_xgb_symbols"
        )
        return {
            "lightgbm": a,
            "xgboost": b,
            "symbols": symbols,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    def list_models(self) -> list[dict[str, Any]]:
        """模型列表。"""
        rows = self.db.scalars(select(MlModel).order_by(MlModel.id.desc())).all()
        return [
            {
                "model_id": r.model_id,
                "engine": r.engine,
                "as_factor": bool(r.as_factor),
                "path": r.path,
                "metrics": json.loads(r.metrics_json or "{}"),
                "features": json.loads(r.features_json or "[]"),
            }
            for r in rows
        ]

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
        target = path.parent if path.suffix else path
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
        elif path.exists():
            path.unlink()
        self.db.delete(row)
        self.db.flush()


class MlInferencer:
    """截面打分（演示：对特征表打分）。"""

    def __init__(self, db: Session):
        self.db = db

    def score(self, model_id: str, X: pd.DataFrame, *, fallback: bool = False) -> pd.Series:
        """按 model_id 加载引擎并打分。"""
        row = self.db.scalar(select(MlModel).where(MlModel.model_id == model_id))
        if not row:
            raise ValueError("model not found")
        backend = get_backend(row.engine)  # type: ignore[arg-type]
        try:
            model = backend.load(Path(row.path))
            if row.engine == "lightgbm":
                return pd.Series(model.predict(X), index=X.index)
            if row.engine == "xgboost":
                import xgboost as xgb

                d = xgb.DMatrix(X)
                return pd.Series(model.predict(d), index=X.index)
            raise ValueError(f"unsupported engine: {row.engine}")
        except Exception:
            if fallback:
                rng = np.random.default_rng(abs(hash(model_id)) % (2**32))
                return pd.Series(rng.random(len(X)), index=X.index)
            raise
