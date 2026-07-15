"""QMT 涨停表现客户端（与 QmtBroker 分离）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from desk_common.symbols import normalize_symbol


class QmtSentimentClient(Protocol):
    """涨停表现拉取协议。"""

    def fetch_limit_performance(self, symbols: list[str], asof: date) -> list[dict[str, Any]]:
        """返回 limitupperformance 风格行列表。"""
        ...


class MockQmtSentimentClient:
    """测试用 Mock。"""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = list(rows or [])
        self.calls: list[tuple[list[str], date]] = []

    def seed(self, rows: list[dict[str, Any]]) -> None:
        """替换种子行。"""
        self._rows = list(rows)

    def fetch_limit_performance(self, symbols: list[str], asof: date) -> list[dict[str, Any]]:
        """按 symbol 过滤种子（忽略 asof，测用）。"""
        syms = {normalize_symbol(s) for s in symbols}
        self.calls.append((sorted(syms), asof))
        out = []
        for r in self._rows:
            sym = normalize_symbol(str(r.get("symbol") or ""))
            if not syms or sym in syms:
                row = dict(r)
                row["symbol"] = sym
                out.append(row)
        return out


class XtdataSentimentClient:
    """
    真实 xtdata limitupperformance 适配。

    import 失败由上层记 failed；字段映射在联调时收紧。
    """

    def __init__(self) -> None:
        from xtquant import xtdata  # type: ignore

        self._xt = xtdata

    def fetch_limit_performance(self, symbols: list[str], asof: date) -> list[dict[str, Any]]:
        """批量拉取（stub：待本机联调完整下载/订阅流程）。"""
        raise NotImplementedError("XtdataSentimentClient 待联调 limitupperformance")
