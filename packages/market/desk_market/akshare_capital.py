"""个股资金流 / 融资余额适配（忽略坏代理）。"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from io import BytesIO
from typing import Any

import pandas as pd
import requests

from desk_common.symbols import normalize_symbol

logger = logging.getLogger(__name__)

_EM_FFLOW_PATH = "/api/qt/stock/fflow/daykline/get"
_EM_HOSTS = (
    "https://push2his.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://1.push2his.eastmoney.com",
    "https://2.push2his.eastmoney.com",
    "https://3.push2his.eastmoney.com",
    "https://4.push2his.eastmoney.com",
    "https://5.push2his.eastmoney.com",
    "https://6.push2his.eastmoney.com",
    "https://7.push2his.eastmoney.com",
    "https://8.push2his.eastmoney.com",
)
_SINA_MONEYFLOW_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "MoneyFlow.ssl_qsfx_zjlrqs"
)
_SSE_MARGIN_URL = "https://query.sse.com.cn/marketdata/tradedata/queryMargin.do"
_SZSE_MARGIN_URL = "https://www.szse.cn/api/report/ShowReport"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _optional_float(value: Any) -> float | None:
    """
    解析可选浮点；失败返回 None。

    @param value: 原始值
    """
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _recent_weekdays(count: int) -> list[date]:
    """
    生成最近若干个工作日（不含周末，不剔除节假日）。

    @param count: 需要的工作日数量
    """
    day = date.today()
    out: list[date] = []
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return out


class AkshareCapitalClient:
    """
    个股日资金流 + 融资余额客户端。

    资金流：东方财富优先（含净占比），不足时新浪兜底。
    融资余额：上交所 / 深交所官方明细。
    """

    def __init__(self, *, timeout: float = 12.0) -> None:
        """
        @param timeout: HTTP 超时秒数
        """
        self._timeout = timeout
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.headers.update(_DEFAULT_HEADERS)

    def fetch_daily(self, symbol: str, days: int = 20) -> list[dict[str, Any]]:
        """
        拉取个股最近 N 个交易日资金流。

        @param symbol: 规范化或可规范化 symbol
        @param days: 最大返回交易日数
        @returns: 含 ts、五档净额，以及可选超大单/大单净占比
        @raises RuntimeError: 全部数据源失败或无有效数据
        """
        sym = normalize_symbol(symbol)
        code, market = sym.split(".", maxsplit=1)
        if market not in {"SH", "SZ", "BJ"}:
            raise RuntimeError(f"capital flow unsupported for {sym}")

        errors: list[str] = []
        em_rows: list[dict[str, Any]] = []
        try:
            em_rows = self._fetch_eastmoney(code=code, market=market, days=days)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"eastmoney: {exc}")
            logger.warning("capital flow eastmoney failed for %s: %s", sym, exc)

        if len(em_rows) >= min(days, 5):
            return em_rows

        try:
            sina_rows = self._fetch_sina(code=code, market=market, days=days)
            if len(sina_rows) > len(em_rows):
                return sina_rows
            if em_rows:
                return em_rows
            if sina_rows:
                return sina_rows
            errors.append("sina returned no rows")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"sina: {exc}")
            logger.warning("capital flow sina failed for %s: %s", sym, exc)
            if em_rows:
                return em_rows

        raise RuntimeError(f"capital flow fetch failed: {'; '.join(errors) or 'no data'}")

    def fetch_margin(self, symbol: str) -> dict[str, Any]:
        """
        拉取融资余额及较上一披露日增减。

        @param symbol: 标的
        @returns: ``balance/change/as_of``
        @raises RuntimeError: 无可用两融明细
        """
        sym = normalize_symbol(symbol)
        code, market = sym.split(".", maxsplit=1)
        if market not in {"SH", "SZ"}:
            raise RuntimeError(f"margin unsupported for {sym}")

        points: list[dict[str, Any]] = []
        for day in _recent_weekdays(15):
            row = (
                self._fetch_margin_sse(code, day)
                if market == "SH"
                else self._fetch_margin_szse(code, day)
            )
            if row is None:
                continue
            points.append(row)
            if len(points) >= 2:
                break

        if not points:
            raise RuntimeError(f"margin balance unavailable for {sym}")

        latest = points[0]
        prev = points[1] if len(points) > 1 else None
        change = None
        if prev is not None:
            change = float(latest["balance"]) - float(prev["balance"])
        return {
            "balance": float(latest["balance"]),
            "change": change,
            "as_of": latest["ts"].isoformat()
            if isinstance(latest["ts"], date)
            else str(latest["ts"]),
        }

    def _fetch_eastmoney(self, *, code: str, market: str, days: int) -> list[dict[str, Any]]:
        """
        东方财富个股日资金流。

        kline：日期,主力,小单,中单,大单,超大单,主力净占比,小单占比,中单占比,大单占比,超大单占比,...
        """
        market_code = 1 if market == "SH" else 0
        params = {
            "lmt": "0",
            "klt": "101",
            "secid": f"{market_code}.{code}",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "_": str(int(time.time() * 1000)),
        }
        last_error: Exception | None = None
        payload: dict[str, Any] | None = None
        for host in _EM_HOSTS:
            try:
                response = self._session.get(
                    f"{host}{_EM_FFLOW_PATH}",
                    params=params,
                    headers={
                        **_DEFAULT_HEADERS,
                        "Referer": "https://data.eastmoney.com/zjlx/detail.html",
                    },
                    timeout=self._timeout,
                )
                response.raise_for_status()
                payload = response.json() or {}
                klines = ((payload.get("data") or {}).get("klines")) or []
                if klines:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                payload = None
                continue
        else:
            if last_error is not None:
                raise RuntimeError(str(last_error)) from last_error
            raise RuntimeError("eastmoney fund flow unreachable")

        klines = ((payload or {}).get("data") or {}).get("klines") or []
        if not klines:
            return []

        records: list[dict[str, Any]] = []
        for item in klines:
            parts = str(item).split(",")
            if len(parts) < 6:
                continue
            ts = pd.to_datetime(parts[0], errors="coerce")
            if pd.isna(ts):
                continue
            try:
                main_net = float(parts[1])
                small_net = float(parts[2])
                medium_net = float(parts[3])
                large_net = float(parts[4])
                super_net = float(parts[5])
            except (TypeError, ValueError):
                continue
            records.append(
                {
                    "ts": ts.date(),
                    "main_net": main_net,
                    "super_net": super_net,
                    "large_net": large_net,
                    "medium_net": medium_net,
                    "small_net": small_net,
                    "super_pct": _optional_float(parts[10]) if len(parts) > 10 else None,
                    "large_pct": _optional_float(parts[9]) if len(parts) > 9 else None,
                }
            )

        records.sort(key=lambda row: row["ts"])
        return records[-days:]

    def _fetch_sina(self, *, code: str, market: str, days: int) -> list[dict[str, Any]]:
        """
        新浪个股资金流向历史。

        仅可靠提供主力净流入与超大单；净占比不可用。
        """
        daima = f"{market.lower()}{code}"
        page_size = max(days, 20)
        response = self._session.get(
            _SINA_MONEYFLOW_URL,
            params={
                "page": "1",
                "num": str(page_size),
                "sort": "opendate",
                "asc": "0",
                "daima": daima,
            },
            headers={**_DEFAULT_HEADERS, "Referer": "https://finance.sina.com.cn/"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, list) or not raw:
            return []

        records: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            ts = pd.to_datetime(item.get("opendate"), errors="coerce")
            if pd.isna(ts):
                continue
            try:
                main_net = float(item.get("netamount"))
                super_net = float(item.get("r0_net"))
            except (TypeError, ValueError):
                continue
            records.append(
                {
                    "ts": ts.date(),
                    "main_net": main_net,
                    "super_net": super_net,
                    "large_net": 0.0,
                    "medium_net": 0.0,
                    "small_net": 0.0,
                    "super_pct": None,
                    "large_pct": None,
                }
            )

        records.sort(key=lambda row: row["ts"])
        return records[-days:]

    def _fetch_margin_sse(self, code: str, day: date) -> dict[str, Any] | None:
        """
        上交所个股融资余额。

        @param code: 6 位代码
        @param day: 交易日
        """
        params = {
            "isPagination": "true",
            "tabType": "mxtype",
            "detailsDate": day.strftime("%Y%m%d"),
            "stockCode": code,
            "pageHelp.pageSize": "10",
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.endPage": "1",
        }
        try:
            response = self._session.get(
                _SSE_MARGIN_URL,
                params=params,
                headers={**_DEFAULT_HEADERS, "Referer": "https://www.sse.com.cn/"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            rows = (response.json() or {}).get("result") or []
        except Exception as exc:  # noqa: BLE001
            logger.debug("sse margin %s %s failed: %s", code, day, exc)
            return None
        for row in rows:
            if str(row.get("stockCode") or "") != code:
                continue
            balance = _optional_float(row.get("rzye"))
            if balance is None:
                return None
            return {"ts": day, "balance": balance}
        return None

    def _fetch_margin_szse(self, code: str, day: date) -> dict[str, Any] | None:
        """
        深交所个股融资余额。

        @param code: 6 位代码
        @param day: 交易日
        """
        params = {
            "SHOWTYPE": "xlsx",
            "CATALOGID": "1837_xxpl",
            "txtDate": day.isoformat(),
            "tab2PAGENO": "1",
            "TABKEY": "tab2",
        }
        try:
            response = self._session.get(
                _SZSE_MARGIN_URL,
                params=params,
                headers={
                    **_DEFAULT_HEADERS,
                    "Referer": "https://www.szse.cn/disclosure/margin/margin/index.html",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            frame = pd.read_excel(BytesIO(response.content), dtype=str)
        except Exception as exc:  # noqa: BLE001
            logger.debug("szse margin %s %s failed: %s", code, day, exc)
            return None
        if frame is None or frame.empty:
            return None

        # 列名随版本略有差异，按位置/关键字兼容
        cols = list(frame.columns)
        code_col = cols[0]
        # 融资余额通常在第 4 列（0 证券代码 1 简称 2 融资买入额 3 融资余额）
        balance_col = None
        for col in cols:
            name = str(col)
            if "融资余额" in name or name.endswith("余额"):
                balance_col = col
                break
        if balance_col is None and len(cols) >= 4:
            balance_col = cols[3]

        for _, row in frame.iterrows():
            raw_code = str(row.get(code_col) or "").replace("&nbsp;", "").strip()
            if raw_code.zfill(6) != code.zfill(6):
                continue
            balance = _optional_float(str(row.get(balance_col) or "").replace(",", ""))
            if balance is None:
                return None
            return {"ts": day, "balance": balance}
        return None
