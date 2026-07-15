"""AkShare 日线补洞适配（输出与 qmt_md 相同列结构）。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from desk_common.symbols import normalize_symbol


def akshare_supports_symbol(symbol: str) -> bool:
    """
    AkShare ``stock_zh_a_hist`` 是否适合补洞。

    北交所东财 secid 映射不可靠，且常被代理打断，故不走 AkShare。
    """
    sym = normalize_symbol(symbol)
    return sym.endswith(".SH") or sym.endswith(".SZ")


class AkshareDailyClient:
    """
    AkShare 日线客户端。

    测试可注入同构 Fake；真实路径按需 import akshare。
    """

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """
        拉取前复权默认列 + *_hfq。

        不支持的市场或网络/代理失败时返回空表（不向调用方抛出长错误栈）。

        @param symbol: 规范化或可规范化 symbol
        @param start: 起始日
        @param end: 结束日
        @returns: 与 MarketService.upsert 兼容的 DataFrame；失败为空
        """
        sym = normalize_symbol(symbol)
        if not akshare_supports_symbol(sym):
            return pd.DataFrame()

        try:
            import akshare as ak  # noqa: PLC0415 — 可选重依赖
        except Exception:  # noqa: BLE001
            return pd.DataFrame()

        code = sym.split(".")[0]
        start_s = start.strftime("%Y%m%d")
        end_s = end.strftime("%Y%m%d")
        try:
            qfq = ak.stock_zh_a_hist(
                symbol=code, period="daily", start_date=start_s, end_date=end_s, adjust="qfq"
            )
            hfq = ak.stock_zh_a_hist(
                symbol=code, period="daily", start_date=start_s, end_date=end_s, adjust="hfq"
            )
        except Exception:  # noqa: BLE001 — ProxyError / 东财限流等
            return pd.DataFrame()
        return _merge_ak_frames(qfq, hfq)


def _merge_ak_frames(qfq: pd.DataFrame, hfq: pd.DataFrame) -> pd.DataFrame:
    """将 AkShare 两套复权表合并为默认列 + *_hfq。"""
    if qfq is None or qfq.empty:
        return pd.DataFrame()

    def _norm(df: pd.DataFrame) -> pd.DataFrame:
        rename = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }
        out = df.rename(columns=rename).copy()
        out["date"] = pd.to_datetime(out["date"]).dt.date
        return out

    q = _norm(qfq)
    h = _norm(hfq) if hfq is not None and not hfq.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    h_by_date = {r["date"]: r for r in h.to_dict("records")} if not h.empty else {}
    for r in q.to_dict("records"):
        hr = h_by_date.get(r["date"], r)
        rows.append(
            {
                "date": r["date"],
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0) or 0),
                "amount": float(r.get("amount", 0) or 0),
                "open_hfq": float(hr["open"]),
                "high_hfq": float(hr["high"]),
                "low_hfq": float(hr["low"]),
                "close_hfq": float(hr["close"]),
                "volume_hfq": float(hr.get("volume", 0) or 0),
            }
        )
    return pd.DataFrame(rows)
