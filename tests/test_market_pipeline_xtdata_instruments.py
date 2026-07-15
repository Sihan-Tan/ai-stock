"""XtdataMarketData：日线双复权与证券列表（保留 ETF）。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from desk_market.qmt_md import (
    XtdataMarketData,
    _expire_means_delisted,
    _map_instrument_status,
)


class _FakeXt:
    """假 xtdata：固定板块与 K 线。"""

    def __init__(self) -> None:
        self.downloaded = False
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def get_stock_list_in_sector(self, sector: str):
        if sector == "沪深A股":
            return ["600519.SH", "000001.SZ", "510300.SH", "830001.BJ"]
        if sector in ("退市股票", "退市"):
            return []
        return []

    def download_sector_data(self) -> None:
        self.downloaded = True

    def get_instrument_detail_list(self, stock_list, iscomplete=False):
        return {
            "600519.SH": {
                "InstrumentName": "贵州茅台",
                "InstrumentStatus": 0,
                "ExpireDate": "99999999",
            },
            "000001.SZ": {
                "InstrumentName": "平安银行",
                "InstrumentStatus": 0,
                "ExpireDate": "10000991",
            },
            "510300.SH": {
                "InstrumentName": "沪深300ETF",
                "InstrumentStatus": 0,
                "ExpireDate": "99999999",
            },
            "830001.BJ": {
                "InstrumentName": "北交示例",
                "InstrumentStatus": 1,
                "ExpireDate": "99999999",
            },
        }

    def download_history_data(self, stock_code, period, start_time="", end_time="", incrementally=None):
        return None

    def get_market_data_ex(
        self,
        field_list=None,
        stock_list=None,
        period="1d",
        start_time="",
        end_time="",
        count=-1,
        dividend_type="none",
        fill_data=True,
    ):
        idx = pd.Index(["20240102", "20240103"])
        if dividend_type == "front":
            df = pd.DataFrame(
                {
                    "open": [10.0, 10.5],
                    "high": [11.0, 11.5],
                    "low": [9.5, 10.0],
                    "close": [10.5, 11.0],
                    "volume": [100.0, 110.0],
                    "amount": [1000.0, 1100.0],
                },
                index=idx,
            )
        else:
            df = pd.DataFrame(
                {
                    "open": [100.0, 105.0],
                    "high": [110.0, 115.0],
                    "low": [95.0, 100.0],
                    "close": [105.0, 110.0],
                    "volume": [100.0, 110.0],
                },
                index=idx,
            )
        code = (stock_list or ["600519.SH"])[0]
        return {code: df}


def test_expire_sentinel_not_delisted():
    assert _expire_means_delisted("10000991") is False
    assert _expire_means_delisted("10011011") is False
    assert _expire_means_delisted("99999999") is False
    assert _expire_means_delisted("20200101") is True
    assert _expire_means_delisted("20991231") is False


def test_map_instrument_status_expire_and_suspend():
    assert _map_instrument_status({"ExpireDate": "99999999", "InstrumentStatus": 0}) == "listed"
    assert _map_instrument_status({"ExpireDate": "10000991", "InstrumentStatus": 0}) == "listed"
    assert _map_instrument_status({"ExpireDate": "20200101", "InstrumentStatus": 0}) == "delisted"
    assert _map_instrument_status({"ExpireDate": "99999999", "InstrumentStatus": 1}) == "suspended"


def test_list_instruments_keeps_etf():
    fake = _FakeXt()
    md = object.__new__(XtdataMarketData)
    md._xt = fake
    rows = md.list_instruments()
    syms = {r.symbol for r in rows}
    assert "600519.SH" in syms
    assert "000001.SZ" in syms
    assert "510300.SH" in syms
    assert "830001.BJ" in syms
    by_sym = {r.symbol: r for r in rows}
    assert by_sym["600519.SH"].name == "贵州茅台"
    assert by_sym["510300.SH"].name == "沪深300ETF"
    assert by_sym["830001.BJ"].status == "suspended"


def test_get_daily_bars_merges_front_and_back():
    fake = _FakeXt()
    md = object.__new__(XtdataMarketData)
    md._xt = fake
    df = md.get_daily_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 5))
    assert len(df) == 2
    assert float(df.iloc[0]["close"]) == 10.5
    assert float(df.iloc[0]["close_hfq"]) == 105.0
    assert "volume_hfq" in df.columns
