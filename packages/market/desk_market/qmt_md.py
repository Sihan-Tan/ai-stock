"""QMT 行情适配：与交易通道 QmtBroker 严格分离。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

import pandas as pd

from desk_common.symbols import normalize_symbol

_HFQ_OHLCV = ("open", "high", "low", "close", "volume")

# 主板块：沪深 A（含 ETF 等成分）+ 京市；不去前缀过滤
_A_SHARE_SECTORS = ("沪深A股", "京市A股", "北交所", "沪深京A股")
_DELISTED_SECTORS = ("退市股票", "退市", "已退市", "退市板块")


@dataclass
class InstrumentInfo:
    """标的元信息（Mock 用字符串 status；真实 xtdata 映射到此）。"""

    symbol: str
    name: str = ""
    status: str = "listed"  # listed|delisted|suspended


class QmtMarketData(Protocol):
    """行情只读协议。"""

    def list_instruments(self) -> list[InstrumentInfo]:
        """列出全部标的元信息。"""
        ...

    def list_a_share_symbols(self, include_delisted: bool = False) -> list[str]:
        """列出 A 股符号；默认排除退市。"""
        ...

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """日线：默认列为前复权，另含 *_hfq 后复权列。"""
        ...

    def get_minute_bars(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
    ) -> pd.DataFrame:
        """分钟 K 线。"""
        ...

    def get_snapshots(self, symbols: list[str]) -> dict[str, dict]:
        """最新快照（只读）。"""
        ...


def _parse_ts(value: str | datetime | date) -> datetime:
    """将日期/时间输入解析为 datetime。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time())
    return pd.Timestamp(value).to_pydatetime()


def _merge_qfq_hfq(qfq: dict[str, Any], hfq: dict[str, Any]) -> dict[str, Any]:
    """合并前复权默认列与后复权 *_hfq 列。"""
    row = dict(qfq)
    for key in _HFQ_OHLCV:
        if key in hfq:
            row[f"{key}_hfq"] = hfq[key]
    if "amount" in hfq and "amount_hfq" not in row:
        row["amount_hfq"] = hfq["amount"]
    return row


def _expire_means_delisted(expire_raw: object) -> bool:
    """
    判断 ExpireDate 是否表示已退市。

    xtdata 对股票常返回 ``10000991`` / ``10011011`` 等非日历哨兵，
    不能按整型与今天比较；仅当值为合理 ``YYYYMMDD``（年在 1990–2099）且早于今天才视为退市。
    """
    expire = str(expire_raw or "").strip()
    if not expire or expire in ("0", "99999999"):
        return False
    if len(expire) != 8 or not expire.isdigit():
        return False
    year = int(expire[:4])
    if year < 1990 or year > 2099:
        return False
    return int(expire) < int(date.today().strftime("%Y%m%d"))


def _map_instrument_status(detail: dict[str, Any] | None) -> str:
    """
    将 xtdata InstrumentDetail 映射为 listed|delisted|suspended。

    @param detail: get_instrument_detail 结果
    """
    if not detail:
        return "listed"
    if _expire_means_delisted(detail.get("ExpireDate")):
        return "delisted"
    st = detail.get("InstrumentStatus")
    if st not in (0, None, "0"):
        return "suspended"
    return "listed"


class MockQmtMarketData:
    """单测用 Mock：固定 InstrumentStatus / OHLCV。"""

    def __init__(self, instruments: list[InstrumentInfo] | None = None) -> None:
        self._instruments: list[InstrumentInfo] = []
        for info in instruments or []:
            self._instruments.append(
                InstrumentInfo(
                    symbol=normalize_symbol(info.symbol),
                    name=info.name,
                    status=info.status,
                )
            )
        self._daily: dict[str, list[dict[str, Any]]] = {}
        self._minute: dict[str, list[dict[str, Any]]] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}

    def list_instruments(self) -> list[InstrumentInfo]:
        """列出全部标的元信息。"""
        return list(self._instruments)

    def list_a_share_symbols(self, include_delisted: bool = False) -> list[str]:
        """列出 A 股符号；默认排除退市。"""
        out: list[str] = []
        for info in self._instruments:
            if not include_delisted and info.status == "delisted":
                continue
            out.append(info.symbol)
        return out

    def seed_daily(
        self,
        symbol: str,
        bar_date: date,
        *,
        qfq: dict[str, Any],
        hfq: dict[str, Any],
    ) -> None:
        """
        写入一条日线种子（前复权 + 后复权）。

        @param symbol: 标的
        @param bar_date: 交易日
        @param qfq: 前复权 OHLCV（及 amount）
        @param hfq: 后复权 OHLCV
        """
        sym = normalize_symbol(symbol)
        row = _merge_qfq_hfq(qfq, hfq)
        row["date"] = bar_date
        self._daily.setdefault(sym, []).append(row)
        self._snapshots.setdefault(sym, {"last": qfq.get("close"), "symbol": sym})

    def seed_minute(
        self,
        symbol: str,
        ts: str | datetime,
        **ohlcv: Any,
    ) -> None:
        """
        写入一条分钟种子。

        @param symbol: 标的
        @param ts: 时间戳
        @param ohlcv: open/high/low/close/volume 等
        """
        sym = normalize_symbol(symbol)
        row = dict(ohlcv)
        row["ts"] = _parse_ts(ts)
        self._minute.setdefault(sym, []).append(row)
        self._snapshots.setdefault(sym, {"last": ohlcv.get("close"), "symbol": sym})

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """日线：默认列为前复权，另含 *_hfq。"""
        sym = normalize_symbol(symbol)
        rows = [
            r
            for r in self._daily.get(sym, [])
            if start <= r["date"] <= end
        ]
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def get_minute_bars(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
    ) -> pd.DataFrame:
        """分钟 K 线。"""
        sym = normalize_symbol(symbol)
        start_ts = _parse_ts(start)
        end_ts = _parse_ts(end)
        rows = [
            r
            for r in self._minute.get(sym, [])
            if start_ts <= r["ts"] <= end_ts
        ]
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def get_snapshots(self, symbols: list[str]) -> dict[str, dict]:
        """最新快照（只读）。"""
        out: dict[str, dict] = {}
        for raw in symbols:
            sym = normalize_symbol(raw)
            if sym in self._snapshots:
                out[sym] = dict(self._snapshots[sym])
        return out


class XtdataMarketData:
    """
    真实 xtquant.xtdata 适配。

    拉数方式对齐 ``example/0/1/8``：connect + 板块过滤 + download_history_data
    + get_market_data_ex(front/back)。
    禁止依赖 desk_broker.QmtBroker。
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

    def _fmt_day(self, d: date) -> str:
        """date → YYYYMMDD。"""
        return d.strftime("%Y%m%d")

    def _stock_list_from_sectors(self) -> list[str]:
        """从板块取代码列表（保留 ETF/板块指数等，不做前缀过滤）；空则 download_sector_data 后重试。"""
        symbols = self._try_sector_lists()
        if symbols:
            return symbols
        try:
            self._xt.download_sector_data()
        except Exception:  # noqa: BLE001
            pass
        return self._try_sector_lists()

    def _try_sector_lists(self) -> list[str]:
        """按候选板块拉取并去重；保留 ETF 与板块相关代码。"""
        seen: set[str] = set()
        ordered: list[str] = []
        for sector in _A_SHARE_SECTORS:
            try:
                xs = self._xt.get_stock_list_in_sector(sector) or []
            except Exception:  # noqa: BLE001
                continue
            for s in xs:
                code = str(s)
                if "." not in code or code in seen:
                    continue
                seen.add(code)
                ordered.append(code)
        return ordered

    def _delisted_symbols(self) -> set[str]:
        """退市板块成分（名称对齐 example）。"""
        out: set[str] = set()
        for sector in _DELISTED_SECTORS:
            try:
                xs = self._xt.get_stock_list_in_sector(sector) or []
            except Exception:  # noqa: BLE001
                continue
            out.update(str(s) for s in xs)
        return out

    def list_instruments(self) -> list[InstrumentInfo]:
        """列出 A 股标的（板块成分过滤 + 合约名称/状态）。"""
        raw_symbols = self._stock_list_from_sectors()
        if not raw_symbols:
            raise RuntimeError("xtdata 未返回 A 股板块成分，请确认 miniQMT 已启动且板块数据已下载")

        delisted = self._delisted_symbols()
        details: dict[str, Any] = {}
        chunk = 500
        for i in range(0, len(raw_symbols), chunk):
            part = raw_symbols[i : i + chunk]
            try:
                batch = self._xt.get_instrument_detail_list(part) or {}
                if isinstance(batch, dict):
                    details.update(batch)
            except Exception:  # noqa: BLE001
                for sym in part:
                    try:
                        d = self._xt.get_instrument_detail(sym)
                        if d:
                            details[sym] = d
                    except Exception:  # noqa: BLE001
                        continue

        out: list[InstrumentInfo] = []
        for raw in raw_symbols:
            sym = normalize_symbol(raw)
            d = details.get(raw) or details.get(sym) or {}
            if raw in delisted or sym in delisted:
                status = "delisted"
            else:
                status = _map_instrument_status(d if isinstance(d, dict) else None)
            out.append(
                InstrumentInfo(
                    symbol=sym,
                    name=str(d.get("InstrumentName") or "") if isinstance(d, dict) else "",
                    status=status,
                )
            )
        return out

    def list_a_share_symbols(self, include_delisted: bool = False) -> list[str]:
        """列出 A 股符号；默认排除退市。"""
        out: list[str] = []
        for info in self.list_instruments():
            if not include_delisted and info.status == "delisted":
                continue
            out.append(info.symbol)
        return out

    def _df_from_market_ex(self, data: Any, symbol: str) -> pd.DataFrame:
        """将 get_market_data_ex 返回规整为带 date 列的 DataFrame。"""
        if not data:
            return pd.DataFrame()
        df = data.get(symbol) if isinstance(data, dict) else None
        if df is None or getattr(df, "empty", True):
            return pd.DataFrame()
        out = df.copy()
        dates: list[date] = []
        for idx in out.index:
            idx_str = str(idx).replace("-", "")[:8]
            if len(idx_str) < 8 or not idx_str.isdigit():
                dates.append(None)  # type: ignore[arg-type]
                continue
            dates.append(date(int(idx_str[:4]), int(idx_str[4:6]), int(idx_str[6:8])))
        out = out.assign()
        out["date"] = dates
        out = out.dropna(subset=["date"])
        return out

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """
        日线双复权：默认列=前复权（front），``*_hfq``=后复权（back）。

        对齐 ``example/8-日线后复权数据.py``。
        """
        symbol = normalize_symbol(symbol)
        start_s = self._fmt_day(start)
        end_s = self._fmt_day(end)
        try:
            self._xt.download_history_data(
                symbol, period="1d", start_time=start_s, end_time=end_s
            )
        except Exception:  # noqa: BLE001 — 本地已有缓存时仍可继续读
            pass

        data_front = self._xt.get_market_data_ex(
            field_list=["open", "high", "low", "close", "volume", "amount"],
            stock_list=[symbol],
            period="1d",
            start_time=start_s,
            end_time=end_s,
            dividend_type="front",
        )
        data_back = self._xt.get_market_data_ex(
            field_list=["open", "high", "low", "close", "volume"],
            stock_list=[symbol],
            period="1d",
            start_time=start_s,
            end_time=end_s,
            dividend_type="back",
        )
        front = self._df_from_market_ex(data_front, symbol)
        back = self._df_from_market_ex(data_back, symbol)
        if front.empty:
            return pd.DataFrame()

        rows: list[dict[str, Any]] = []
        back_by_date: dict[date, Any] = {}
        if not back.empty:
            for _, brow in back.iterrows():
                back_by_date[brow["date"]] = brow

        for _, frow in front.iterrows():
            d = frow["date"]
            if d < start or d > end:
                continue
            qfq = {
                "date": d,
                "open": float(frow["open"]) if pd.notna(frow.get("open")) else None,
                "high": float(frow["high"]) if pd.notna(frow.get("high")) else None,
                "low": float(frow["low"]) if pd.notna(frow.get("low")) else None,
                "close": float(frow["close"]) if pd.notna(frow.get("close")) else None,
                "volume": float(frow["volume"]) if pd.notna(frow.get("volume")) else 0.0,
                "amount": float(frow["amount"]) if "amount" in frow and pd.notna(frow.get("amount")) else 0.0,
            }
            brow = back_by_date.get(d)
            if brow is not None:
                hfq = {
                    "open": float(brow["open"]) if pd.notna(brow.get("open")) else qfq["open"],
                    "high": float(brow["high"]) if pd.notna(brow.get("high")) else qfq["high"],
                    "low": float(brow["low"]) if pd.notna(brow.get("low")) else qfq["low"],
                    "close": float(brow["close"]) if pd.notna(brow.get("close")) else qfq["close"],
                    "volume": float(brow["volume"]) if pd.notna(brow.get("volume")) else qfq["volume"],
                }
            else:
                hfq = {
                    "open": qfq["open"],
                    "high": qfq["high"],
                    "low": qfq["low"],
                    "close": qfq["close"],
                    "volume": qfq["volume"],
                }
            if None in (qfq["open"], qfq["high"], qfq["low"], qfq["close"]):
                continue
            if None in (hfq["open"], hfq["high"], hfq["low"], hfq["close"]):
                continue
            rows.append(_merge_qfq_hfq(qfq, hfq))

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def get_minute_bars(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
    ) -> pd.DataFrame:
        """分钟 K 线（download + get_market_data_ex period=1m）。"""
        symbol = normalize_symbol(symbol)
        start_ts = _parse_ts(start)
        end_ts = _parse_ts(end)
        start_s = start_ts.strftime("%Y%m%d%H%M%S")
        end_s = end_ts.strftime("%Y%m%d%H%M%S")
        try:
            self._xt.download_history_data(
                symbol, period="1m", start_time=start_s, end_time=end_s
            )
        except Exception:  # noqa: BLE001
            pass
        data = self._xt.get_market_data_ex(
            field_list=["open", "high", "low", "close", "volume", "amount"],
            stock_list=[symbol],
            period="1m",
            start_time=start_s,
            end_time=end_s,
            dividend_type="none",
        )
        if not data:
            return pd.DataFrame()
        df = data.get(symbol) if isinstance(data, dict) else None
        if df is None or getattr(df, "empty", True):
            return pd.DataFrame()
        out = df.copy()
        out["ts"] = [pd.Timestamp(i).to_pydatetime() for i in out.index]
        out = out[(out["ts"] >= start_ts) & (out["ts"] <= end_ts)]
        return out.reset_index(drop=True)

    def get_snapshots(self, symbols: list[str]) -> dict[str, dict]:
        """最新快照（instrument detail 中的 PreClose 等，能取则返回）。"""
        out: dict[str, dict] = {}
        for raw in symbols:
            sym = normalize_symbol(raw)
            try:
                d = self._xt.get_instrument_detail(sym) or {}
            except Exception:  # noqa: BLE001
                continue
            if not d:
                continue
            out[sym] = {
                "symbol": sym,
                "name": d.get("InstrumentName") or "",
                "last": d.get("PreClose"),
                "pre_close": d.get("PreClose"),
            }
        return out
