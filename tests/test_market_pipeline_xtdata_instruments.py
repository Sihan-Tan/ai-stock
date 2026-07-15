"""XtdataMarketData.list_instruments 板块映射。"""

from __future__ import annotations

from desk_market.qmt_md import XtdataMarketData, _expire_means_delisted, _map_instrument_status


class _FakeXt:
    """假 xtdata：固定板块与详情。"""

    def __init__(self) -> None:
        self.downloaded = False

    def get_stock_list_in_sector(self, sector: str):
        if sector == "沪深京A股":
            return ["600519.SH", "000001.SZ", "430047.BJ"]
        return []

    def download_sector_data(self) -> None:
        self.downloaded = True

    def get_instrument_detail_list(self, stock_list, iscomplete=False):
        return {
            "600519.SH": {"InstrumentName": "贵州茅台", "InstrumentStatus": 0, "ExpireDate": "99999999"},
            "000001.SZ": {"InstrumentName": "平安银行", "InstrumentStatus": 0, "ExpireDate": "10000991"},
            "430047.BJ": {"InstrumentName": "诺思兰德", "InstrumentStatus": 1, "ExpireDate": "99999999"},
        }


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


def test_list_instruments_from_sector(monkeypatch):
    fake = _FakeXt()
    md = object.__new__(XtdataMarketData)
    md._xt = fake
    rows = md.list_instruments()
    assert len(rows) == 3
    by_sym = {r.symbol: r for r in rows}
    assert by_sym["600519.SH"].name == "贵州茅台"
    assert by_sym["600519.SH"].status == "listed"
    assert by_sym["430047.BJ"].status == "suspended"
    assert "000001.SZ" in md.list_a_share_symbols(include_delisted=False)
