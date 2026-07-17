"""QMT 行情适配：与交易通道 QmtBroker 严格分离。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import logging
from typing import Any, Protocol

import pandas as pd

from desk_common.symbols import normalize_symbol

_HFQ_OHLCV = ("open", "high", "low", "close", "volume")
# 竞价窗右端（含）；xtdata tick 下载 end_time 用 09:30:00（秒级），勿带微秒后缀
_AUCTION_END = time(9, 29, 59)
_AUCTION_DOWNLOAD_END = time(9, 30, 0)
_LOGGER = logging.getLogger(__name__)

# 主板块：沪深 A（含 ETF 等成分）+ 京市；不去前缀过滤
_A_SHARE_SECTORS = ("沪深A股", "京市A股", "北交所", "沪深京A股")
_DELISTED_SECTORS = ("退市股票", "退市", "已退市", "退市板块")


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


def _turnover_rate(
    *,
    volume_lots: float | None,
    volume_shares: float | None,
    float_shares: float | None,
) -> float | None:
    """
    按流通股本计算换手率（%）。

    xtdata 日/分钟成交量多为「手」；tick ``pvolume`` 为股。
    换手率 = 成交股数 / 流通股本 × 100。

    @param volume_lots: 成交量（手）
    @param volume_shares: 成交量（股）
    @param float_shares: 流通股本（股）
    """
    if float_shares is None or float_shares <= 0:
        return None
    shares = volume_shares
    if shares is None and volume_lots is not None:
        shares = volume_lots * 100.0
    if shares is None or shares <= 0:
        return None
    return shares / float_shares * 100.0


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


def _fmt_qmt_datetime(ts: datetime) -> str:
    """
    datetime → YYYYMMDDHHMMSS（xtdata 历史下载时间串）。

    tick 接口不接受微秒后缀；带 ``ffffff`` 会触发「结束时间错误」。
    """
    return ts.strftime("%Y%m%d%H%M%S")


def _side_level_number(value: Any) -> float | None:
    """
    解析买卖一档价/量；支持标量或 list/tuple 首档。

    @param value: askPrice/bidPrice/askVol/bidVol 原始值
    """
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return _first_number(value[0])
    try:
        # numpy 数组等
        if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
            if len(value) == 0:
                return None
            return _first_number(value[0])
    except TypeError:
        pass
    return _first_number(value)


def _auction_tick_price(row: dict[str, Any]) -> float | None:
    """
    集合竞价 tick 价格：成交价优先，否则用虚拟撮合价（买卖一价）。

    QMT 在 09:15–09:24 的 ``lastPrice`` 常为 0，参考价在 askPrice/bidPrice[0]。
    """
    last = _first_number(
        row.get("last"),
        row.get("lastPrice"),
        row.get("LastPrice"),
        row.get("last_price"),
        row.get("close"),
    )
    if last is not None and last > 0:
        return last
    for key in ("askPrice", "bidPrice", "ask_price", "bid_price"):
        price = _side_level_number(row.get(key))
        if price is not None and price > 0:
            return price
    return None


def _auction_tick_volume(row: dict[str, Any]) -> tuple[str, float]:
    """
    集合竞价 tick 量：真实成交量优先，否则用一档虚拟匹配量（累计口径）。

    @returns: ``(\"abs\"|\"cum\", value)``
    """
    volume = _first_number(
        row.get("volume"),
        row.get("Volume"),
        row.get("pvolume"),
        row.get("pVolume"),
    )
    if volume is not None and volume > 0:
        return "abs", volume
    for key in ("askVol", "bidVol", "ask_vol", "bid_vol"):
        matched = _side_level_number(row.get(key))
        if matched is not None and matched > 0:
            return "cum", matched
    return "abs", 0.0


def _auction_window(
    start: datetime, end: datetime
) -> tuple[datetime, datetime] | None:
    """返回查询窗口与当日集合竞价的交集。"""
    if start.date() != end.date():
        return None
    auction_start = datetime.combine(start.date(), time(9, 15))
    auction_end = datetime.combine(start.date(), _AUCTION_END)
    if start > auction_end or end < auction_start:
        return None
    return max(start, auction_start), min(end, auction_end)


def _fill_auction_minutes(
    minute_df: pd.DataFrame,
    tick_rows: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    用 tick 聚合缺失的 09:15–09:29 分钟 K 线。

    @param minute_df: 已取得的分钟 K 线
    @param tick_rows: 含 ts/last/volume/amount 的 tick 行
    @param start: 查询起始时间
    @param end: 查询结束时间
    @returns: 补齐后的分钟 K 线
    """
    window = _auction_window(start, end)
    if window is None or not tick_rows:
        return minute_df
    window_start, window_end = window

    existing_minutes: set[datetime] = set()
    if not minute_df.empty and "ts" in minute_df:
        for value in minute_df["ts"]:
            try:
                existing_minutes.add(pd.Timestamp(value).floor("min").to_pydatetime())
            except (TypeError, ValueError):
                continue

    grouped: dict[datetime, list[tuple[datetime, float, str, float, float]]] = {}
    for row in tick_rows:
        try:
            tick_ts = _parse_ts(row["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        minute = pd.Timestamp(tick_ts).floor("min").to_pydatetime()
        if minute in existing_minutes or not (window_start <= tick_ts <= window_end):
            continue
        price = _auction_tick_price(row)
        if price is None:
            continue
        vol_kind, volume = _auction_tick_volume(row)
        amount = _first_number(row.get("amount"), row.get("Amount"), row.get("turnover"))
        grouped.setdefault(minute, []).append(
            (
                tick_ts,
                price,
                vol_kind,
                volume,
                amount if amount is not None else 0.0,
            )
        )

    rows: list[dict[str, Any]] = []
    for minute, values in grouped.items():
        values.sort(key=lambda value: value[0])
        prices = [value[1] for value in values]
        abs_vols = [value[3] for value in values if value[2] == "abs" and value[3] > 0]
        cum_vols = [value[3] for value in values if value[2] == "cum"]
        if abs_vols:
            # 竞价确认成交等多用「最新真实量」
            minute_volume = float(abs_vols[-1])
        elif cum_vols:
            minute_volume = float(max(0.0, cum_vols[-1] - cum_vols[0]))
            if minute_volume == 0.0 and cum_vols[-1] > 0:
                # 该分钟虚拟量未变：仍记末值，避免整段无量柱
                minute_volume = float(cum_vols[-1])
        else:
            minute_volume = 0.0
        rows.append(
            {
                "ts": minute,
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "volume": minute_volume,
                "amount": sum(value[4] for value in values),
            }
        )
    if not rows:
        return minute_df
    out = pd.concat([minute_df, pd.DataFrame(rows)], ignore_index=True, sort=False)
    return out.sort_values("ts").reset_index(drop=True)


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
        self._ticks: dict[str, list[dict[str, Any]]] = {}
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
        float_volume: float | None = None,
    ) -> None:
        """
        写入一条日线种子（前复权 + 后复权）。

        @param symbol: 标的
        @param bar_date: 交易日
        @param qfq: 前复权 OHLCV（及 amount）
        @param hfq: 后复权 OHLCV
        @param float_volume: 可选流通股本（股），用于快照换手率
        """
        sym = normalize_symbol(symbol)
        row = _merge_qfq_hfq(qfq, hfq)
        row["date"] = bar_date
        self._daily.setdefault(sym, []).append(row)
        snap = self._snapshots.setdefault(sym, {"symbol": sym})
        snap["last"] = qfq.get("close")
        if qfq.get("volume") is not None:
            snap["volume"] = qfq.get("volume")
        if qfq.get("amount") is not None:
            snap["amount"] = qfq.get("amount")
        if float_volume is not None:
            snap["float_volume"] = float_volume
        turnover = _turnover_rate(
            volume_lots=_first_number(snap.get("volume")),
            volume_shares=None,
            float_shares=_first_number(snap.get("float_volume")),
        )
        if turnover is not None:
            snap["turnover_rate"] = turnover

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
        snap = self._snapshots.setdefault(sym, {"symbol": sym})
        snap["last"] = ohlcv.get("close")
        if ohlcv.get("volume") is not None:
            snap["volume"] = ohlcv.get("volume")
        if ohlcv.get("amount") is not None:
            snap["amount"] = ohlcv.get("amount")

    def seed_ticks(self, symbol: str, rows: list[dict[str, Any]]) -> None:
        """
        写入多条 tick 种子。

        @param symbol: 标的
        @param rows: 含 ts/last/volume/amount 的 tick 行
        """
        sym = normalize_symbol(symbol)
        seeded: list[dict[str, Any]] = []
        for row in rows:
            tick = dict(row)
            tick["ts"] = _parse_ts(tick["ts"])
            seeded.append(tick)
        self._ticks.setdefault(sym, []).extend(seeded)

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
        return _fill_auction_minutes(
            pd.DataFrame(rows),
            self._ticks.get(sym, []),
            start_ts,
            end_ts,
        )

    def get_snapshots(self, symbols: list[str]) -> dict[str, dict]:
        """最新快照（只读）。"""
        out: dict[str, dict] = {}
        for raw in symbols:
            sym = normalize_symbol(raw)
            if sym not in self._snapshots:
                continue
            snap = dict(self._snapshots[sym])
            last = snap.get("last")
            pre = snap.get("pre_close")
            if pre is None and last is not None:
                pre = last
                snap["pre_close"] = pre
            if snap.get("pct_chg") is None and last is not None and pre:
                snap["pct_chg"] = (float(last) - float(pre)) / float(pre) * 100.0
            if snap.get("turnover_rate") is None:
                turnover = _turnover_rate(
                    volume_lots=_first_number(snap.get("volume")),
                    volume_shares=_first_number(snap.get("pvolume")),
                    float_shares=_first_number(snap.get("float_volume")),
                )
                if turnover is not None:
                    snap["turnover_rate"] = turnover
            out[sym] = snap
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

    def _merge_front_back(
        self,
        symbol: str,
        front: pd.DataFrame,
        back: pd.DataFrame,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """将前/后复权 DataFrame（含 date 列）合并为 upsert 行。"""
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
                "amount": float(frow["amount"])
                if "amount" in frow and pd.notna(frow.get("amount"))
                else 0.0,
            }
            brow = back_by_date.get(d)
            if brow is not None:
                hfq = {
                    "open": float(brow["open"]) if pd.notna(brow.get("open")) else qfq["open"],
                    "high": float(brow["high"]) if pd.notna(brow.get("high")) else qfq["high"],
                    "low": float(brow["low"]) if pd.notna(brow.get("low")) else qfq["low"],
                    "close": float(brow["close"]) if pd.notna(brow.get("close")) else qfq["close"],
                    "volume": float(brow["volume"])
                    if pd.notna(brow.get("volume"))
                    else qfq["volume"],
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
        return self._merge_front_back(symbol, front, back, start, end)

    def get_daily_bars_batch(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """
        批量日线（对齐 ``example/1``：先逐只 download，再批量 get_market_data_ex）。

        @param symbols: 代码列表
        @param start: 起始日
        @param end: 结束日
        @returns: symbol → DataFrame
        """
        syms = [normalize_symbol(s) for s in symbols]
        if not syms:
            return {}
        start_s = self._fmt_day(start)
        end_s = self._fmt_day(end)
        for sym in syms:
            try:
                self._xt.download_history_data(
                    sym, period="1d", start_time=start_s, end_time=end_s
                )
            except Exception:  # noqa: BLE001
                continue

        data_front = self._xt.get_market_data_ex(
            field_list=["open", "high", "low", "close", "volume", "amount"],
            stock_list=syms,
            period="1d",
            start_time=start_s,
            end_time=end_s,
            dividend_type="front",
        )
        data_back = self._xt.get_market_data_ex(
            field_list=["open", "high", "low", "close", "volume"],
            stock_list=syms,
            period="1d",
            start_time=start_s,
            end_time=end_s,
            dividend_type="back",
        )
        out: dict[str, pd.DataFrame] = {}
        for sym in syms:
            front = self._df_from_market_ex(data_front, sym)
            back = self._df_from_market_ex(data_back, sym)
            out[sym] = self._merge_front_back(sym, front, back, start, end)
        return out

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
        out = pd.DataFrame()
        if not data:
            return self._ensure_auction_minutes(symbol, out, start_ts, end_ts)
        df = data.get(symbol) if isinstance(data, dict) else None
        if df is not None and not getattr(df, "empty", True):
            out = df.copy()
            out["ts"] = [pd.Timestamp(i).to_pydatetime() for i in out.index]
            out = out[(out["ts"] >= start_ts) & (out["ts"] <= end_ts)].reset_index(
                drop=True
            )
        return self._ensure_auction_minutes(symbol, out, start_ts, end_ts)

    def _ensure_auction_minutes(
        self,
        symbol: str,
        minute_df: pd.DataFrame,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        在 1 分钟行情缺失时以 QMT tick 补齐集合竞价分钟。

        @param symbol: 标的
        @param minute_df: 已取得的分钟 K 线
        @param start: 查询起始时间
        @param end: 查询结束时间
        @returns: 补齐后的分钟 K 线；tick 拉取失败时返回原结果
        """
        window = _auction_window(start, end)
        if window is None:
            return minute_df
        auction_start = datetime.combine(start.date(), time(9, 15))
        auction_end = datetime.combine(start.date(), _AUCTION_DOWNLOAD_END)
        start_s = _fmt_qmt_datetime(auction_start)
        end_s = _fmt_qmt_datetime(auction_end)
        try:
            self._xt.download_history_data(
                symbol,
                period="tick",
                start_time=start_s,
                end_time=end_s,
            )
            data = self._xt.get_market_data_ex(
                field_list=[
                    "lastPrice",
                    "volume",
                    "amount",
                    "askPrice",
                    "bidPrice",
                    "askVol",
                    "bidVol",
                ],
                stock_list=[symbol],
                period="tick",
                start_time=start_s,
                end_time=end_s,
                dividend_type="none",
            )
            tick_df = data.get(symbol) if isinstance(data, dict) else None
            if tick_df is None or getattr(tick_df, "empty", True):
                return minute_df
            tick_rows: list[dict[str, Any]] = []
            for tick_ts, tick in tick_df.iterrows():
                row = tick.to_dict()
                row["ts"] = tick_ts
                tick_rows.append(row)
            return _fill_auction_minutes(minute_df, tick_rows, start, end)
        except Exception:  # noqa: BLE001 — tick 缓存或字段差异不能影响分钟行情
            _LOGGER.warning(
                "QMT tick 聚合集合竞价分钟失败: symbol=%s", symbol, exc_info=True
            )
            return minute_df

    def get_snapshots(self, symbols: list[str]) -> dict[str, dict]:
        """
        最新快照：优先 full_tick 最新价/量额，其次 InstrumentDetail；并计算涨跌幅。

        @returns: symbol → {symbol,name,last,pre_close,pct_chg,volume,amount,turnover_rate}
        """
        out: dict[str, dict] = {}
        syms = [normalize_symbol(s) for s in symbols if s and str(s).strip()]
        ticks: dict[str, Any] = {}
        if syms:
            try:
                ticks = self._xt.get_full_tick(syms) or {}
            except Exception:  # noqa: BLE001
                ticks = {}

        for sym in syms:
            try:
                d = self._xt.get_instrument_detail(sym) or {}
            except Exception:  # noqa: BLE001
                d = {}
            tick = ticks.get(sym) if isinstance(ticks, dict) else None
            if not isinstance(tick, dict):
                tick = {}

            last = _first_number(
                tick.get("lastPrice"),
                tick.get("LastPrice"),
                d.get("LastPrice"),
                d.get("lastPrice"),
            )
            pre_close = _first_number(
                tick.get("lastClose"),
                tick.get("LastClose"),
                tick.get("preClose"),
                d.get("PreClose"),
                d.get("preClose"),
            )
            # 无最新价时不要用昨充数，避免涨跌幅恒为 0
            if last is None:
                last = pre_close

            pct_chg = None
            if last is not None and pre_close is not None and pre_close != 0:
                pct_chg = (last - pre_close) / pre_close * 100.0

            volume = _first_number(
                tick.get("volume"),
                tick.get("Volume"),
                tick.get("pvolume"),
                d.get("LastVolume"),
            )
            # tick.volume 为手；pvolume 为股。优先用手，避免与 pvolume 混用。
            volume_lots = _first_number(tick.get("volume"), tick.get("Volume"), d.get("LastVolume"))
            volume_shares = _first_number(tick.get("pvolume"), tick.get("pVolume"))
            amount = _first_number(
                tick.get("amount"),
                tick.get("Amount"),
            )
            float_shares = _first_number(d.get("FloatVolume"), d.get("floatVolume"))
            turnover_rate = _turnover_rate(
                volume_lots=volume_lots,
                volume_shares=volume_shares,
                float_shares=float_shares,
            )
            # 快照 volume 字段：优先手；若只有股则回退股数
            if volume_lots is not None:
                volume = volume_lots
            elif volume_shares is not None:
                volume = volume_shares

            if not d and not tick:
                continue
            out[sym] = {
                "symbol": sym,
                "name": d.get("InstrumentName") or tick.get("InstrumentName") or "",
                "last": last,
                "pre_close": pre_close,
                "pct_chg": pct_chg,
                "volume": volume,
                "amount": amount,
                "float_volume": float_shares,
                "turnover_rate": turnover_rate,
            }
        return out
