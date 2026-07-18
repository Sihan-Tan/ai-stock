"""
精简 ML 概率引擎（对齐 CASE ``ml_strategy``，无强依赖 talib）。

特征用 pandas + ``desk_indicators``；模型可切 xgboost/lightgbm。
滚动训练支持增量：实例内缓存模型，避免每根 bar 全量重训。
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from desk_indicators import compute

ModelType = Literal["xgboost", "lightgbm"]

FEATURE_COLS = [
    "ret_1d",
    "ret_5d",
    "ret_10d",
    "vol_ratio_5d",
    "amplitude_5d",
    "hist_vol_20d",
    "momentum_5d",
    "momentum_20d",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "boll_pos",
    "ma5_bias",
    "ma20_bias",
]


def make_labels(close: pd.Series, horizon: int = 1) -> pd.Series:
    """二分类标签：未来 horizon 日涨=1。"""
    future_ret = close.shift(-horizon) / close - 1.0
    return (future_ret > 0).astype(int)


def calc_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    从 OHLCV 计算轻量特征（约 15 列）。

    @param df: 需含 open/high/low/close/volume
    @returns: 原列 + 特征列
    """
    out = df.copy()
    if "close" not in out.columns:
        raise ValueError("df 缺少 close")
    out = compute(out, specs=["SMA_5", "SMA_20", "RSI_14", "MACD", "BOLL"])
    c = out["close"].astype(float)
    h = out["high"].astype(float) if "high" in out.columns else c
    lo = out["low"].astype(float) if "low" in out.columns else c
    v = out["volume"].astype(float) if "volume" in out.columns else pd.Series(0.0, index=out.index)

    out["ret_1d"] = c.pct_change(1)
    out["ret_5d"] = c.pct_change(5)
    out["ret_10d"] = c.pct_change(10)
    out["amplitude_5d"] = (h.rolling(5).max() - lo.rolling(5).min()) / c.rolling(5).mean().replace(
        0, np.nan
    )
    avg_vol_5 = v.rolling(5).mean().replace(0, np.nan)
    out["vol_ratio_5d"] = v / avg_vol_5
    out["hist_vol_20d"] = out["ret_1d"].rolling(20).std() * np.sqrt(252)
    out["momentum_5d"] = c.pct_change(5)
    out["momentum_20d"] = c.pct_change(20)

    boll_u = out.get("boll_upper")
    boll_l = out.get("boll_lower")
    if boll_u is not None and boll_l is not None:
        width = (boll_u - boll_l).replace(0, np.nan)
        out["boll_pos"] = (c - boll_l) / width
    else:
        out["boll_pos"] = np.nan

    sma5 = out.get("sma_5")
    sma20 = out.get("sma_20")
    out["ma5_bias"] = (c - sma5) / sma5.replace(0, np.nan) if sma5 is not None else np.nan
    out["ma20_bias"] = (c - sma20) / sma20.replace(0, np.nan) if sma20 is not None else np.nan
    return out


def preprocess_features(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """整段 MAD 截断 + Z-score（与 CASE 口径接近的轻量版）。"""
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            continue
        s = out[col].astype(float)
        med = s.median()
        mad = (s - med).abs().median()
        if mad and mad > 0:
            clipped = s.clip(med - 5 * mad, med + 5 * mad)
        else:
            clipped = s
        mu = clipped.mean()
        sigma = clipped.std()
        out[col] = (clipped - mu) / sigma if sigma and sigma > 0 else 0.0
    return out


def _train_model(model_type: ModelType, X: np.ndarray, y: np.ndarray):
    """训练二分类器。"""
    if model_type == "lightgbm":
        import lightgbm as lgb

        model = lgb.LGBMClassifier(
            n_estimators=80,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        model.fit(X, y)
        return model

    import xgboost as xgb

    model = xgb.XGBClassifier(
        n_estimators=80,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X, y)
    return model


class RollingProbState:
    """跨 bar 复用的滚动训练状态。"""

    def __init__(
        self,
        *,
        train_days: int = 120,
        retrain_interval: int = 20,
        horizon: int = 1,
        model_type: ModelType = "xgboost",
    ):
        self.train_days = train_days
        self.retrain_interval = retrain_interval
        self.horizon = horizon
        self.model_type = model_type
        self.model = None
        self.last_train_i = -retrain_interval
        self.last_n = 0
        self.last_prob = 0.5

    def predict_last(self, history: pd.DataFrame) -> float:
        """
        对当前 history 末根输出涨概率；必要时重训。

        @param history: 升序 OHLCV（可含 date）
        @returns: 0~1 概率；样本不足返回 0.5
        """
        n = len(history)
        if n < self.train_days + 30:
            self.last_n = n
            self.last_prob = 0.5
            return 0.5

        feat = calc_features(history)
        feat["label"] = make_labels(feat["close"].astype(float), horizon=self.horizon)
        cols = [c for c in FEATURE_COLS if c in feat.columns]
        feat = preprocess_features(feat, cols)

        # 标签末 horizon 行无效，预测点取可训窗口末
        i = n - 1 - self.horizon
        if i < self.train_days:
            self.last_prob = 0.5
            self.last_n = n
            return 0.5

        need_train = self.model is None or (i - self.last_train_i) >= self.retrain_interval
        if need_train:
            train = feat.iloc[max(0, i - self.train_days) : i]
            clean = train.dropna(subset=cols + ["label"])
            if len(clean) < max(40, self.train_days // 3):
                self.last_prob = 0.5
                self.last_n = n
                return 0.5
            y = clean["label"].astype(int).values
            if len(np.unique(y)) < 2:
                self.last_prob = 0.5
                self.last_n = n
                return 0.5
            X = clean[cols].astype(float).values
            self.model = _train_model(self.model_type, X, y)
            self.last_train_i = i

        row = feat.iloc[i]
        if row[cols].isna().any():
            self.last_prob = 0.5
            self.last_n = n
            return 0.5
        X_test = row[cols].astype(float).values.reshape(1, -1)
        prob = float(self.model.predict_proba(X_test)[0, 1])
        self.last_prob = prob
        self.last_n = n
        return prob


def run_ml_prob_last(
    history: pd.DataFrame,
    state: RollingProbState | None = None,
    **params: Any,
) -> tuple[float, RollingProbState]:
    """
    便捷入口：返回末根概率与状态。

    @param history: 日线 OHLCV
    @param state: 可复用状态；None 则新建
    @param params: 传给 RollingProbState 的构造参数
    """
    st = state or RollingProbState(**params)
    return st.predict_last(history), st
