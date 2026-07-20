"""选股因子与 TA-Lib 序列。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from desk_factor.registry import get_factor, list_enabled_registry
from desk_indicators import apply_factor_specs, last_engine
from desk_indicators import compute as compute_indicators
from desk_market import MarketService


class FactorService:
    """因子目录与基于日线的序列计算。"""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def list_factors(self) -> list[dict[str, Any]]:
        """返回注册表可见因子（含 plot / default_enabled）。"""
        return [dict(f) for f in list_enabled_registry()]

    def compute_series_from_df(self, ohlcv: pd.DataFrame, names: list[str]) -> dict[str, Any]:
        """
        在内存 OHLCV 上计算因子序列。

        @raises ValueError: 未知因子名
        """
        resolved = []
        for raw in names:
            meta = get_factor(raw)
            if meta is None:
                raise ValueError(f"unknown factor: {raw}")
            resolved.append(meta)

        specs = [
            {"talib": m["talib"], "params": m["params"], "outputs": m["outputs"]}
            for m in resolved
        ]
        df = apply_factor_specs(ohlcv, specs)
        bars = [
            {
                "date": str(r["date"])[:10] if not isinstance(r["date"], str) else r["date"][:10],
                "o": float(r["open"]),
                "h": float(r["high"]),
                "l": float(r["low"]),
                "c": float(r["close"]),
                "v": float(r["volume"]),
            }
            for _, r in df.iterrows()
        ]
        series: dict[str, Any] = {}
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
        return {"engine": last_engine(), "bars": bars, "series": series}

    def compute_series(
        self,
        symbol: str,
        names: list[str],
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """
        从 bars_daily 加载并计算。

        @raises ValueError: 无日线或未知因子
        """
        if self.db is None:
            raise ValueError("db required")
        end = end or date.today()
        start = start or date(end.year - 1, end.month, end.day)
        df = MarketService(self.db).load_daily_df(symbol, start, end)
        if df.empty:
            raise ValueError("无本地日线")
        out = self.compute_series_from_df(df, names)
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
