"""AkShare 个股资金流适配。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from desk_common.symbols import normalize_symbol


class AkshareCapitalClient:
    """
    AkShare 个股日资金流客户端。

    测试可注入实现同一 ``fetch_daily`` 接口的 Fake。
    """

    def fetch_daily(self, symbol: str, days: int = 20) -> list[dict[str, Any]]:
        """
        拉取个股最近 N 个交易日资金流。

        @param symbol: 规范化或可规范化 symbol
        @param days: 最大返回交易日数
        @returns: 含 ts 与五档净流入金额的记录，按日期升序
        @raises RuntimeError: AkShare 不可用、请求失败或无有效数据
        """
        sym = normalize_symbol(symbol)
        code, market = sym.split(".", maxsplit=1)
        if market not in {"SH", "SZ"}:
            raise RuntimeError(f"AkShare capital flow unsupported for {sym}")

        try:
            import akshare as ak  # noqa: PLC0415 — 可选重依赖

            raw = ak.stock_individual_fund_flow(stock=code, market=market.lower())
        except Exception as exc:  # noqa: BLE001 — 网络、代理、限流等均交给调用方降级
            raise RuntimeError(f"AkShare capital flow fetch failed: {exc}") from exc

        if raw is None or raw.empty:
            raise RuntimeError("AkShare capital flow returned no data")

        required = {
            "日期": "ts",
            "主力净流入-净额": "main_net",
            "超大单净流入-净额": "super_net",
            "大单净流入-净额": "large_net",
            "中单净流入-净额": "medium_net",
            "小单净流入-净额": "small_net",
        }
        missing = set(required).difference(raw.columns)
        if missing:
            raise RuntimeError(f"AkShare capital flow missing columns: {sorted(missing)}")

        frame = raw.rename(columns=required)[list(required.values())].copy()
        frame["ts"] = pd.to_datetime(frame["ts"], errors="coerce").dt.date
        for key in required.values():
            if key != "ts":
                frame[key] = pd.to_numeric(frame[key], errors="coerce")
        frame = frame.dropna().sort_values("ts").tail(days)
        if frame.empty:
            raise RuntimeError("AkShare capital flow contains no valid rows")

        return [
            {
                "ts": row["ts"],
                "main_net": float(row["main_net"]),
                "super_net": float(row["super_net"]),
                "large_net": float(row["large_net"]),
                "medium_net": float(row["medium_net"]),
                "small_net": float(row["small_net"]),
            }
            for row in frame.to_dict(orient="records")
        ]
