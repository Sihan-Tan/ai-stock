"""QMT 涨停表现客户端（与 QmtBroker 分离）。"""

from __future__ import annotations

from datetime import date
import logging
from typing import Any, Protocol

from desk_common.symbols import normalize_symbol

_LOGGER = logging.getLogger(__name__)


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


def _first_number(*values: Any) -> float | None:
    """取第一个可解析数字。"""
    for value in values:
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:
            return number
    return None


def _row_from_limit_frame(symbol: str, frame_row: Any) -> dict[str, Any] | None:
    """
    将 xtdata limitupperformance 一行映射为聚合器字段。

    @param symbol: 标的
    @param frame_row: Series / dict
    """
    if hasattr(frame_row, "to_dict"):
        raw = frame_row.to_dict()
    elif isinstance(frame_row, dict):
        raw = dict(frame_row)
    else:
        return None

    # 兼容若干字段别名
    direct = raw.get("direct")
    if direct is None:
        # 部分版本用 type / limitType：1 涨停 2 跌停
        direct = raw.get("type") or raw.get("LimitType") or raw.get("limitType")
    try:
        direct_i = int(direct) if direct is not None else 0
    except (TypeError, ValueError):
        direct_i = 0

    seal = _first_number(
        raw.get("sealCount"),
        raw.get("SealCount"),
        raw.get("board_height"),
        raw.get("limitTimes"),
    )
    break_up = _first_number(
        raw.get("breakUp"),
        raw.get("BreakUp"),
        raw.get("break_times"),
    )
    up_amount = _first_number(
        raw.get("upAmount"),
        raw.get("UpAmount"),
        raw.get("sealAmount"),
        raw.get("fd_amount"),
    )
    name = str(raw.get("name") or raw.get("InstrumentName") or "").strip()
    concept = str(raw.get("concept") or raw.get("Concept") or "").strip()

    if direct_i not in (1, 2) and seal is None and up_amount is None:
        return None

    return {
        "symbol": normalize_symbol(symbol),
        "name": name,
        "direct": direct_i if direct_i in (1, 2) else 1,
        "sealCount": int(seal or 1),
        "breakUp": int(break_up or 0),
        "upAmount": float(up_amount or 0.0),
        "concept": concept,
    }


class XtdataSentimentClient:
    """
    真实 xtdata ``limitupperformance`` 适配。

    按批 download + get_market_data_ex；单标的失败跳过，不中断整批。
    """

    def __init__(self) -> None:
        from xtquant import xtdata  # type: ignore

        self._xt = xtdata

    def fetch_limit_performance(self, symbols: list[str], asof: date) -> list[dict[str, Any]]:
        """
        批量拉取涨停表现。

        @param symbols: 标的列表
        @param asof: 交易日
        """
        day = asof.strftime("%Y%m%d")
        start_s = f"{day}000000"
        end_s = f"{day}235959"
        syms = [normalize_symbol(s) for s in symbols if s and str(s).strip()]
        out: list[dict[str, Any]] = []
        # 分批避免一次过大
        batch_size = 80
        for i in range(0, len(syms), batch_size):
            batch = syms[i : i + batch_size]
            for sym in batch:
                try:
                    self._xt.download_history_data(
                        sym, period="limitupperformance", start_time=start_s, end_time=end_s
                    )
                except Exception:  # noqa: BLE001
                    continue
            try:
                data = self._xt.get_market_data_ex(
                    field_list=[],
                    stock_list=batch,
                    period="limitupperformance",
                    start_time=start_s,
                    end_time=end_s,
                    dividend_type="none",
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("limitupperformance batch failed: %s", exc)
                continue
            if not isinstance(data, dict):
                continue
            for sym in batch:
                frame = data.get(sym)
                if frame is None or getattr(frame, "empty", True):
                    continue
                try:
                    # 取当日最后一行
                    last = frame.iloc[-1]
                except Exception:  # noqa: BLE001
                    continue
                mapped = _row_from_limit_frame(sym, last)
                if mapped is not None:
                    out.append(mapped)
        return out
