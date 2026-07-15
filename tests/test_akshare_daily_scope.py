"""AkShare 补洞适用范围。"""

from desk_market.akshare_daily import AkshareDailyClient, akshare_supports_symbol


def test_akshare_supports_sh_sz_not_bj():
    assert akshare_supports_symbol("600519.SH")
    assert akshare_supports_symbol("000001.SZ")
    assert not akshare_supports_symbol("821008.BJ")


def test_akshare_client_returns_empty_for_bj():
    df = AkshareDailyClient().get_daily_bars(
        "821008.BJ", __import__("datetime").date(2024, 1, 1), __import__("datetime").date(2024, 1, 5)
    )
    assert df.empty
