"""QMT 财务数据适配：与行情 qmt_md 分离，可 Mock。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

import pandas as pd

from desk_common.symbols import normalize_symbol

_STANDARD_KEYS: tuple[str, ...] = (
    "period",
    "revenue",
    "net_profit",
    "gross_margin",
    "net_margin",
    "roe",
    "debt_ratio",
    "eps",
    "bps",
    "operating_cashflow",
    "total_assets",
    "total_liab",
    "total_equity",
    "total_shares",
)

# 标准 key → QMT 列名别名（按优先级）
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "period": ("period", "m_timetag", "reportDate", "endDate", "m_anntime"),
    "revenue": ("revenue", "revenue_inc", "total_operating_revenue"),
    "net_profit": (
        "net_profit",
        "net_profit_incl_min_int_inc",
        "net_profit_excl_min_int_inc",
    ),
    "gross_margin": ("sales_gross_profit", "gross_profit", "gross_margin"),
    "net_margin": ("net_profit", "net_margin"),
    "roe": ("du_return_on_equity", "equity_roe", "net_roe", "roe"),
    "debt_ratio": ("gear_ratio", "debt_ratio", "asset_liability_ratio"),
    "eps": ("s_fa_eps_basic", "s_fa_eps_diluted", "eps", "adjusted_earnings_per_share"),
    "bps": ("s_fa_bps", "bps"),
    "operating_cashflow": (
        "net_cash_flows_oper_act",
        "operating_cashflow",
        "s_fa_ocfps",
    ),
    "total_assets": ("tot_assets", "total_assets"),
    "total_liab": ("tot_liab", "total_liab", "total_liability"),
    "total_equity": ("total_equity", "tot_liab_shrhldr_eqy"),
    "total_shares": ("total_capital", "total_shares", "circulating_capital"),
}


def _first_number(*values: Any) -> float | None:
    """
    取第一个可解析为有限浮点数的值。

    @param values: 候选字段
    """
    for value in values:
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:  # not NaN
            return number
    return None


def _normalize_period(value: Any) -> str | None:
    """
    将 QMT / 各类报告期字段归一为 ``YYYYMMDD``。

    @param value: 毫秒时间戳、整型或字符串
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1e11:
            return datetime.fromtimestamp(number / 1000).strftime("%Y%m%d")
        if 19000000 < number < 21000000:
            return str(int(number))
    text = str(value).strip().replace("-", "").replace("/", "")[:8]
    if len(text) == 8 and text.isdigit():
        return text
    try:
        return pd.Timestamp(value).strftime("%Y%m%d")
    except (TypeError, ValueError):
        return None


def _cutoff_period(years: int) -> str:
    """最近 ``years`` 个自然年的报告期下界（含）。"""
    start_year = date.today().year - max(years, 1) + 1
    return f"{start_year}0101"


def _map_qmt_row(raw: dict[str, Any]) -> dict[str, Any]:
    """
    将 QMT 原始行映射为标准 schema；缺失字段为 ``None``。

    @param raw: 原始字段 dict
    """
    out: dict[str, Any] = {}
    period_values = [_normalize_period(raw.get(alias)) for alias in _FIELD_ALIASES["period"]]
    out["period"] = next((p for p in period_values if p), None)
    for key in _STANDARD_KEYS:
        if key == "period":
            continue
        values = [_first_number(raw.get(alias)) for alias in _FIELD_ALIASES[key]]
        out[key] = next((v for v in values if v is not None), None)
    return out


def _dataframe_to_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame → 标准行列表。"""
    if df is None or getattr(df, "empty", True):
        return []
    rows: list[dict[str, Any]] = []
    for record in df.to_dict(orient="records"):
        rows.append(_map_qmt_row(record))
    return rows


def _filter_by_years(rows: list[dict[str, Any]], years: int) -> list[dict[str, Any]]:
    """按报告期保留最近 ``years`` 年。"""
    cutoff = _cutoff_period(years)
    kept = [row for row in rows if row.get("period") and str(row["period"]) >= cutoff]
    kept.sort(key=lambda row: str(row.get("period") or ""), reverse=True)
    return kept


def _build_response(
    symbol: str,
    tables: dict[str, list[dict[str, Any]]],
    *,
    source: str,
) -> dict[str, Any]:
    """组装统一返回结构。"""
    return {
        "source": source,
        "symbol": symbol,
        "tables": tables,
    }


class QmtFinancials(Protocol):
    """QMT 财务只读协议。"""

    def get_financials(
        self, symbol: str, tables: list[str], years: int = 5
    ) -> dict[str, Any]:
        """
        返回 ``{source, symbol, tables: {name: [row...]}}`` 或抛异常。

        @param symbol: 标的代码
        @param tables: QMT 表名，如 Income / Pershareindex
        @param years: 最近若干自然年
        """
        ...


class MockQmtFinancials:
    """单测用 Mock：内存固定财务表。"""

    def __init__(self, data: dict | None = None, *, fail: bool = False) -> None:
        """
        @param data: ``symbol → table → [row...]``
        @param fail: 为 True 时 ``get_financials`` 直接抛错
        """
        self._data = data or {}
        self._fail = fail

    def get_financials(
        self, symbol: str, tables: list[str], years: int = 5
    ) -> dict[str, Any]:
        """
        返回 Mock 财务表。

        @param symbol: 标的
        @param tables: 请求的表名列表
        @param years: 报告期窗口
        """
        if self._fail:
            raise RuntimeError("mock qmt financials failure")
        sym = normalize_symbol(symbol)
        sym_data = self._data.get(sym)
        if sym_data is None:
            raise RuntimeError(f"mock qmt: no data for {sym}")
        out_tables: dict[str, list[dict[str, Any]]] = {}
        for table in tables:
            rows = list(sym_data.get(table, []))
            out_tables[table] = _filter_by_years(rows, years)
        return _build_response(sym, out_tables, source="qmt")


class XtdataFinancials:
    """
    真实 xtquant.xtdata 财务适配。

    ``download_financial_data`` + ``get_financial_data``；字段映射到标准 key。
    """

    def __init__(self) -> None:
        from xtquant import xtdata  # type: ignore

        try:
            xtdata.enable_hello = False
        except Exception:  # noqa: BLE001
            pass
        self._xt = xtdata
        try:
            self._xt.connect()
        except Exception:  # noqa: BLE001
            pass

    def get_financials(
        self, symbol: str, tables: list[str], years: int = 5
    ) -> dict[str, Any]:
        """
        从本机 QMT 拉取财务表并归一化。

        @param symbol: 标的
        @param tables: QMT 表名
        @param years: 最近若干自然年
        """
        sym = normalize_symbol(symbol)
        if not tables:
            raise RuntimeError("xtdata financials: tables must not be empty")
        start_time = _cutoff_period(years)
        end_time = date.today().strftime("%Y%m%d")
        try:
            self._xt.download_financial_data([sym], table_list=list(tables))
        except Exception:  # noqa: BLE001 — 本地已有缓存时仍可继续读
            pass
        try:
            raw = self._xt.get_financial_data(
                [sym],
                table_list=list(tables),
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"xtdata get_financial_data failed: {exc}") from exc
        if not raw or sym not in raw:
            raise RuntimeError(f"xtdata financials: no data for {sym}")
        sym_tables = raw.get(sym) or {}
        out_tables: dict[str, list[dict[str, Any]]] = {}
        for table in tables:
            table_df = sym_tables.get(table)
            if isinstance(table_df, pd.DataFrame):
                rows = _filter_by_years(_dataframe_to_rows(table_df), years)
            elif isinstance(table_df, list):
                rows = _filter_by_years([_map_qmt_row(dict(r)) for r in table_df], years)
            else:
                rows = []
            out_tables[table] = rows
        if not any(out_tables.values()):
            raise RuntimeError(f"xtdata financials: empty tables for {sym}")
        return _build_response(sym, out_tables, source="qmt")
