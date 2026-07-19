"""AkShare 财务降级适配（输出结构与 QMT 一致）。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from desk_common.symbols import normalize_symbol
from desk_market.qmt_financials import _filter_by_years, _map_qmt_row, _normalize_period

_AK_PERSHARE_COLUMNS: dict[str, tuple[str, ...]] = {
    "period": ("报告期", "日期"),
    "eps": ("基本每股收益(元)", "每股收益(元)", "摊薄每股收益(元)"),
    "roe": ("净资产收益率(%)", "加权净资产收益率(%)", "摊薄净资产收益率(%)"),
    "bps": ("每股净资产(元)",),
    "operating_cashflow": ("每股经营现金流(元)", "每股经营活动产生的现金流量净额(元)"),
    "debt_ratio": ("资产负债率(%)",),
    "gross_margin": ("销售毛利率(%)", "毛利率(%)"),
    "net_margin": ("销售净利率(%)", "净利率(%)"),
}

_AK_INCOME_COLUMNS: dict[str, tuple[str, ...]] = {
    "period": ("报告期",),
    "revenue": ("营业总收入", "营业收入"),
    "net_profit": ("净利润", "归属于母公司所有者的净利润", "归母净利润"),
}

_AK_BALANCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "period": ("报告期",),
    "total_assets": ("资产总计", "总资产"),
    "total_liab": ("负债合计", "总负债"),
    "total_equity": ("所有者权益合计", "股东权益合计"),
}

_AK_CASHFLOW_COLUMNS: dict[str, tuple[str, ...]] = {
    "period": ("报告期",),
    "operating_cashflow": ("经营活动产生的现金流量净额",),
}


def _pick_column(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    """在 DataFrame 列名中查找首个匹配别名。"""
    columns = {str(col).strip(): col for col in df.columns}
    for alias in aliases:
        if alias in columns:
            return str(columns[alias])
    return None


def _rows_from_indicator(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    ``stock_financial_analysis_indicator`` → Pershareindex 标准行。

    @param df: akshare 指标表
    """
    if df is None or df.empty:
        return []
    period_col = _pick_column(df, _AK_PERSHARE_COLUMNS["period"])
    if not period_col:
        return []
    rows: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        raw: dict[str, Any] = {}
        period = _normalize_period(series.get(period_col))
        if not period:
            continue
        raw["period"] = period
        for key, aliases in _AK_PERSHARE_COLUMNS.items():
            if key == "period":
                continue
            col = _pick_column(df, aliases)
            if col is not None:
                raw[key] = series.get(col)
        rows.append(_map_qmt_row(raw))
    return rows


def _rows_from_abstract(df: pd.DataFrame, metric_map: dict[str, tuple[str, ...]]) -> list[dict[str, Any]]:
    """
    财务摘要宽表（指标 × 报告期列）→ 标准行。

    @param df: akshare 摘要表
    @param metric_map: 标准 key → 指标行名称别名
    """
    if df is None or df.empty:
        return []
    option_col = _pick_column(df, ("选项", "指标", "指标名称"))
    if not option_col:
        return []
    period_cols = [
        col
        for col in df.columns
        if col != option_col and _normalize_period(str(col).replace("年", "").replace("月", "").replace("日", ""))
    ]
    if not period_cols:
        period_cols = [col for col in df.columns if col != option_col]
    by_period: dict[str, dict[str, Any]] = {}
    for _, series in df.iterrows():
        metric_name = str(series.get(option_col) or "").strip()
        target_key = None
        for key, aliases in metric_map.items():
            if key == "period":
                continue
            if any(alias in metric_name for alias in aliases):
                target_key = key
                break
        if not target_key:
            continue
        for col in period_cols:
            period = _normalize_period(str(col))
            if not period:
                continue
            bucket = by_period.setdefault(period, {"period": period})
            bucket[target_key] = series.get(col)
    return [_map_qmt_row(raw) for raw in by_period.values()]


def _raw_fetch(code: str, years: int = 5) -> dict[str, list[dict[str, Any]]]:
    """
    调用 akshare 拉取原始财务表（单测可 monkeypatch）。

    @param code: 6 位 A 股代码
    @param years: 最近若干自然年
    @returns: ``table_name → [row...]``（尚未按 years 裁剪）
    """
    try:
        import akshare as ak  # noqa: PLC0415 — 可选重依赖
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"akshare import failed: {exc}") from exc

    start_year = str(date.today().year - max(years, 1) + 1)
    tables: dict[str, list[dict[str, Any]]] = {}

    try:
        indicator = ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
        tables["Pershareindex"] = _rows_from_indicator(indicator)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"akshare Pershareindex failed for {code}: {exc}") from exc

    try:
        abstract = ak.stock_financial_abstract(symbol=code)
        income_rows = _rows_from_abstract(abstract, _AK_INCOME_COLUMNS)
        if income_rows:
            tables["Income"] = income_rows
    except Exception:  # noqa: BLE001 — 摘要缺失不阻断其它表
        pass

    for table_name, sina_symbol in (
        ("Balance", "资产负债表"),
        ("CashFlow", "现金流量表"),
    ):
        try:
            report = ak.stock_financial_report_sina(stock=code, symbol=sina_symbol)
            metric_map = _AK_BALANCE_COLUMNS if table_name == "Balance" else _AK_CASHFLOW_COLUMNS
            rows = _rows_from_abstract(report, metric_map)
            if rows:
                tables[table_name] = rows
        except Exception:  # noqa: BLE001
            continue

    if not any(tables.values()):
        raise RuntimeError(f"akshare returned no financial tables for {code}")
    return tables


def fetch_akshare_financials(symbol: str, years: int = 5) -> dict[str, Any]:
    """
    akshare → 与 QMT 相同 tables 结构；``source=akshare``。

    @param symbol: 原始或可规范化 symbol
    @param years: 最近若干自然年
    @returns: ``{source, symbol, tables}``
    """
    sym = normalize_symbol(symbol)
    code = sym.split(".")[0]
    if not code.isdigit() or len(code) != 6:
        raise RuntimeError(f"akshare financials: unsupported symbol {sym}")

    raw_tables = _raw_fetch(code, years=years)
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, rows in raw_tables.items():
        tables[name] = _filter_by_years(list(rows), years)
    if not any(tables.values()):
        raise RuntimeError(f"akshare financials: empty after filter for {sym}")
    return {
        "source": "akshare",
        "symbol": sym,
        "tables": tables,
    }
