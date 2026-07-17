"""MockQmtMarketData：列表过滤与双复权日线。"""

from datetime import date

from desk_market.qmt_md import InstrumentInfo, MockQmtMarketData


def test_list_instruments_filters_delisted():
    md = MockQmtMarketData(
        instruments=[
            InstrumentInfo(symbol="600519.SH", name="茅台", status="listed"),
            InstrumentInfo(symbol="000001.SZ", name="退市样例", status="delisted"),
        ]
    )
    active = md.list_a_share_symbols(include_delisted=False)
    assert active == ["600519.SH"]
    assert "000001.SZ" in md.list_a_share_symbols(include_delisted=True)


def test_get_daily_bars_returns_qfq_and_hfq_columns():
    md = MockQmtMarketData()
    md.seed_daily(
        "600519.SH",
        date(2024, 1, 2),
        qfq={"open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1, "amount": 1},
        hfq={"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1},
    )
    df = md.get_daily_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 3))
    assert "close" in df.columns and "close_hfq" in df.columns
    assert float(df.iloc[0]["close"]) == 10.5
    assert float(df.iloc[0]["close_hfq"]) == 105.0


def test_get_minute_and_snapshot_readonly():
    md = MockQmtMarketData()
    md.seed_minute(
        "600519.SH",
        "2024-01-02 09:31:00",
        open=10,
        high=10,
        low=10,
        close=10,
        volume=100,
        amount=1000,
    )
    m = md.get_minute_bars("600519.SH", start="2024-01-02 09:30:00", end="2024-01-02 15:00:00")
    assert len(m) == 1
    q = md.get_snapshots(["600519.SH"])
    assert "600519.SH" in q
    assert q["600519.SH"]["volume"] == 100
    assert q["600519.SH"]["amount"] == 1000
