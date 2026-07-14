"""选股因子（表达式/占位）。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from desk_indicators import compute


class FactorService:
    """因子计算：基于指标列。"""

    def list_factors(self) -> list[dict[str, Any]]:
        """内置因子目录。"""
        return [
            {"name": "RSI_14", "source": "TA-Lib", "update": "日更"},
            {"name": "MACD_HIST", "source": "TA-Lib", "update": "日更"},
            {"name": "AMOUNT_Z20", "source": "脚本", "update": "日更"},
        ]

    def compute(self, ohlcv: pd.DataFrame, universe_asof: Any = None) -> pd.DataFrame:
        """产出特征矩阵。"""
        df = compute(ohlcv)
        if "amount" in df.columns:
            df["amount_z20"] = (
                df["amount"] - df["amount"].rolling(20).mean()
            ) / df["amount"].rolling(20).std()
        return df
