"""资金流客户端解析单测。"""

from __future__ import annotations

from datetime import date

from desk_market.akshare_capital import AkshareCapitalClient


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def test_fetch_eastmoney_parses_klines(monkeypatch):
    client = AkshareCapitalClient()

    def fake_get(url, params=None, headers=None, timeout=None):
        if "fflow/daykline" in url:
            # 返回足够多天，避免触发新浪兜底；index9=大单占比,index10=超大单占比
            klines = [
                f"2026-07-{day:02d},100,10,20,30,40,1.1,0,0,-0.5,2.5,1,0,0,0" for day in range(1, 12)
            ]
            return _FakeResp({"data": {"klines": klines}})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(client._session, "get", fake_get)
    rows = client.fetch_daily("600519.SH", days=10)
    assert len(rows) == 10
    assert rows[-1]["main_net"] == 100.0
    assert rows[-1]["small_net"] == 10.0
    assert rows[-1]["medium_net"] == 20.0
    assert rows[-1]["large_net"] == 30.0
    assert rows[-1]["super_net"] == 40.0
    assert rows[-1]["large_pct"] == -0.5
    assert rows[-1]["super_pct"] == 2.5


def test_fetch_falls_back_to_sina(monkeypatch):
    client = AkshareCapitalClient()
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if "fflow/daykline" in url:
            raise RuntimeError("em down")
        assert "MoneyFlow.ssl_qsfx_zjlrqs" in url
        return _FakeResp(
            [
                {
                    "opendate": "2026-07-17",
                    "netamount": "123.4",
                    "r0_net": "56.7",
                },
                {
                    "opendate": "2026-07-16",
                    "netamount": "10",
                    "r0_net": "2",
                },
            ]
        )

    monkeypatch.setattr(client._session, "get", fake_get)
    rows = client.fetch_daily("600519.SH", days=10)
    assert calls["n"] >= 2
    assert len(rows) == 2
    assert rows[-1]["main_net"] == 123.4
    assert rows[-1]["super_net"] == 56.7
    assert rows[-1]["large_net"] == 0.0
    assert rows[-1]["super_pct"] is None


def test_fetch_margin_sse(monkeypatch):
    client = AkshareCapitalClient()

    def fake_get(url, params=None, headers=None, timeout=None):
        day = params["detailsDate"]
        if day.endswith("17") or day.endswith("16"):
            balance = "1100000000" if day.endswith("17") else "1000000000"
            return _FakeResp({"result": [{"stockCode": "600519", "rzye": balance}]})
        return _FakeResp({"result": []})

    monkeypatch.setattr(client._session, "get", fake_get)
    monkeypatch.setattr(
        "desk_market.akshare_capital._recent_weekdays",
        lambda count: [date(2026, 7, 17), date(2026, 7, 16), date(2026, 7, 15)],
    )

    result = client.fetch_margin("600519.SH")
    assert result["balance"] == 1.1e9
    assert result["change"] == 1e8
    assert result["as_of"] == "2026-07-17"
