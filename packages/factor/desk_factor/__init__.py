"""选股因子与 TA-Lib 序列。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_db.models import MlModel
from desk_factor.registry import get_factor, list_enabled_registry
from desk_indicators import apply_factor_specs, last_engine
from desk_indicators import compute as compute_indicators
from desk_market import MarketService

# 日历日预热下限：覆盖 SMA_60 等常用周期 + 节假日空档
_MIN_WARMUP_CALENDAR_DAYS = 120
_ML_PREFIX = "ml:"


def _period_values(params: dict[str, Any]) -> list[int]:
    """从因子参数中提取周期类整数。"""
    out: list[int] = []
    for key, value in params.items():
        key_l = key.lower()
        if not isinstance(value, (int, float)):
            continue
        if "period" in key_l or key_l.endswith("len") or key_l in {"timeperiod", "nbdevup", "nbdevdn"}:
            if "nbdev" in key_l:
                continue
            out.append(int(value))
    return out


def warmup_calendar_days(names: list[str]) -> int:
    """
    按勾选因子估算预热日历天数（交易日缺口用倍率放大）。

    @param names 因子名列表
    """
    max_period = 60
    has_ml = False
    for raw in names:
        if str(raw).startswith(_ML_PREFIX):
            has_ml = True
            continue
        meta = get_factor(raw)
        if meta is None:
            continue
        for period in _period_values(dict(meta.get("params") or {})):
            max_period = max(max_period, period)
        # MACD 等固定慢线未进 timeperiod 时至少按 35 估
        talib_name = str(meta.get("talib") or "").upper()
        if talib_name in {"MACD", "MACDEXT", "MACDFIX"}:
            max_period = max(max_period, 35)
        if talib_name in {"TEMA", "T3"}:
            max_period = max(max_period, 60)
    # 交易日 → 日历日（周末/长假）；ml: 特征含 20 日波动等，至少下限
    days = max(_MIN_WARMUP_CALENDAR_DAYS, int(max_period * 2.5) + 40)
    if has_ml:
        days = max(days, _MIN_WARMUP_CALENDAR_DAYS)
    return days


def slice_series_result(
    result: dict[str, Any],
    start: date,
    end: date,
) -> dict[str, Any]:
    """
    将 bars / series 裁到 [start, end]（含）。

    @param result compute_series_from_df 产物
    @param start 可见起点
    @param end 可见终点
    """
    start_s = start.isoformat()
    end_s = end.isoformat()

    bars = [b for b in result.get("bars") or [] if start_s <= str(b.get("date", ""))[:10] <= end_s]
    series: dict[str, Any] = {}
    for name, block in (result.get("series") or {}).items():
        outputs: dict[str, list[dict[str, Any]]] = {}
        for col, points in (block.get("outputs") or {}).items():
            outputs[col] = [
                p for p in points if start_s <= str(p.get("date", ""))[:10] <= end_s
            ]
        series[name] = {"outputs": outputs}
    out = dict(result)
    out["bars"] = bars
    out["series"] = series
    return out


def _bars_from_ohlcv(ohlcv: pd.DataFrame) -> list[dict[str, Any]]:
    """从 OHLCV DataFrame 构建 bars 列表。"""
    return [
        {
            "date": str(r["date"])[:10] if not isinstance(r["date"], str) else r["date"][:10],
            "o": float(r["open"]),
            "h": float(r["high"]),
            "l": float(r["low"]),
            "c": float(r["close"]),
            "v": float(r["volume"]),
        }
        for _, r in ohlcv.iterrows()
    ]


def _split_factor_names(names: list[str]) -> tuple[list[str], list[str]]:
    """拆分 TA 因子名与 ml: 前缀名。"""
    ta_names: list[str] = []
    ml_names: list[str] = []
    for raw in names:
        if str(raw).startswith(_ML_PREFIX):
            ml_names.append(str(raw))
        else:
            ta_names.append(str(raw))
    return ta_names, ml_names


class FactorService:
    """因子目录与基于日线的序列计算。"""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def list_factors(self) -> list[dict[str, Any]]:
        """返回注册表可见因子，并合并已放入因子列表的 ML 模型。"""
        rows = [dict(f) for f in list_enabled_registry()]
        if self.db is None:
            return rows
        ml_rows = self.db.scalars(
            select(MlModel).where(MlModel.as_factor.is_(True)).order_by(MlModel.id.desc())
        ).all()
        for r in ml_rows:
            rows.append(
                {
                    "name": f"{_ML_PREFIX}{r.model_id}",
                    "label": f"{r.model_id}（{r.engine}）",
                    "category": "ml",
                    "params": {"model_id": r.model_id, "engine": r.engine},
                    "outputs": ["ml_score"],
                    "plot": "panel",
                    "default_enabled": False,
                    "enabled": True,
                    "talib": "",
                }
            )
        return rows

    def _resolve_ml_model(self, name: str) -> MlModel:
        """
        解析 ml:{model_id}，要求已放入因子列表。

        @raises ValueError: 无 db / 未登记 / 未 as_factor
        """
        if self.db is None:
            raise ValueError("db required for ml factors")
        model_id = name[len(_ML_PREFIX) :]
        row = self.db.scalar(select(MlModel).where(MlModel.model_id == model_id))
        if row is None or not bool(row.as_factor):
            raise ValueError(f"ml factor not in factor list or as_factor off: {name}")
        return row

    def _ml_score_series(self, ohlcv: pd.DataFrame, name: str, row: MlModel) -> dict[str, Any]:
        """对日线计算 ml_score 序列（特征缺失行为 None）。"""
        from desk_ml import MlInferencer
        from desk_strategy.ml_prob_engine import FEATURE_COLS, calc_features, preprocess_features

        feats = calc_features(ohlcv)
        feature_cols = list(json.loads(row.features_json or "[]") or FEATURE_COLS)
        feature_cols = [c for c in feature_cols if c in feats.columns]
        if not feature_cols:
            feature_cols = [c for c in FEATURE_COLS if c in feats.columns]

        valid = feats[feature_cols].notna().all(axis=1) if feature_cols else pd.Series(False, index=feats.index)
        score_by_idx: dict[Any, float] = {}
        if bool(valid.any()):
            X = preprocess_features(feats.loc[valid].copy(), feature_cols)[feature_cols]
            scores = MlInferencer(self.db).score(row.model_id, X)
            for idx, val in scores.items():
                if pd.isna(val):
                    continue
                score_by_idx[idx] = float(val)

        points: list[dict[str, Any]] = []
        for idx, r in ohlcv.iterrows():
            d = str(r["date"])[:10] if not isinstance(r["date"], str) else r["date"][:10]
            points.append({"date": d, "v": score_by_idx.get(idx)})
        return {"outputs": {"ml_score": points}}

    def compute_series_from_df(self, ohlcv: pd.DataFrame, names: list[str]) -> dict[str, Any]:
        """
        在内存 OHLCV 上计算因子序列（含 ml: 打分）。

        @raises ValueError: 未知因子名或 ML 未放入因子列表
        """
        ta_names, ml_names = _split_factor_names(names)

        series: dict[str, Any] = {}
        engine = last_engine()
        bars = _bars_from_ohlcv(ohlcv)

        if ta_names:
            resolved = []
            for raw in ta_names:
                meta = get_factor(raw)
                if meta is None:
                    raise ValueError(f"unknown factor: {raw}")
                resolved.append(meta)

            specs = [
                {"talib": m["talib"], "params": m["params"], "outputs": m["outputs"]}
                for m in resolved
            ]
            df = apply_factor_specs(ohlcv, specs)
            engine = last_engine()
            bars = _bars_from_ohlcv(df)
            for meta in resolved:
                outputs: dict[str, list[dict[str, Any]]] = {}
                for col in meta["outputs"]:
                    points = []
                    for _, r in df.iterrows():
                        d = str(r["date"])[:10]
                        val = r[col]
                        points.append({"date": d, "v": None if pd.isna(val) else float(val)})
                    outputs[col] = points
                series[meta["name"]] = {"outputs": outputs}

        for ml_name in ml_names:
            row = self._resolve_ml_model(ml_name)
            series[ml_name] = self._ml_score_series(ohlcv, ml_name, row)

        return {"engine": engine, "bars": bars, "series": series}

    def compute_series(
        self,
        symbol: str,
        names: list[str],
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """
        从 bars_daily 加载并计算。

        会向前多取预热日线，使可见区间左端因子已有值；响应仍只返回 [start, end]。

        @raises ValueError: 无日线或未知因子
        """
        if self.db is None:
            raise ValueError("db required")
        end = end or date.today()
        start = start or date(end.year - 1, end.month, end.day)
        load_start = start - timedelta(days=warmup_calendar_days(names))
        df = MarketService(self.db).load_daily_df(symbol, load_start, end)
        if df.empty:
            raise ValueError("无本地日线")
        out = self.compute_series_from_df(df, names)
        out = slice_series_result(out, start, end)
        if not out["bars"]:
            raise ValueError("无本地日线")
        out["symbol"] = symbol
        return out

    def compute(self, ohlcv: pd.DataFrame, universe_asof: Any = None) -> pd.DataFrame:
        """产出特征矩阵。"""
        df = compute_indicators(ohlcv)
        if "amount" in df.columns:
            df["amount_z20"] = (
                df["amount"] - df["amount"].rolling(20).mean()
            ) / df["amount"].rolling(20).std()
        return df
