"""AkShare 龙虎榜适配。"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from desk_common.symbols import normalize_symbol

_INST_KEYWORDS = ("机构专用", "机构席位", "社保", "券商自营")


class LhbClient(Protocol):
    """龙虎榜拉取协议。"""

    def fetch_by_date(self, asof: date) -> list[dict[str, Any]]:
        """
        返回上榜列表，每项含 symbol/name/reason/net_buy/seats。

        seats: [{side, seat_name, amount}, ...]
        """
        ...


class FakeLhbClient:
    """测试 Fake。"""

    def __init__(self, payload: list[dict[str, Any]] | None = None) -> None:
        self._payload = list(payload or [])
        self.calls: list[date] = []

    def fetch_by_date(self, asof: date) -> list[dict[str, Any]]:
        self.calls.append(asof)
        return list(self._payload)


class AkshareLhbClient:
    """AkShare 实现（函数名集中于此，便于以后替换）。"""

    def fetch_by_date(self, asof: date) -> list[dict[str, Any]]:
        """
        拉取当日龙虎榜。

        优先 stock_lhb_detail_em；失败抛异常由任务层捕获。
        """
        import akshare as ak  # noqa: PLC0415

        day = asof.strftime("%Y%m%d")
        # 东财龙虎榜详情（列名随 akshare 版本可能变化，做宽松映射）
        df = ak.stock_lhb_detail_em(start_date=day, end_date=day)
        if df is None or df.empty:
            return []
        rows: list[dict[str, Any]] = []
        for _, r in df.iterrows():
            code = str(r.get("代码") or r.get("股票代码") or "")
            name = str(r.get("名称") or r.get("股票名称") or "")
            reason = str(r.get("上榜原因") or r.get("解读") or "")
            net = float(r.get("净买额") or r.get("龙虎榜净买额") or 0 or 0)
            sym = normalize_symbol(code)
            rows.append(
                {
                    "symbol": sym,
                    "name": name,
                    "reason": reason,
                    "net_buy": net,
                    "seats": [],  # 明细接口若无席位则留空；另途可补
                }
            )
        return rows


def is_institution_seat(name: str) -> bool:
    """粗判机构席位。"""
    return any(k in name for k in _INST_KEYWORDS)
