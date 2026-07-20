"""AkShare 情绪客户端映射单测（不联网）。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from desk_sentiment.akshare_client import AkshareSentimentClient, FallbackSentimentClient


def test_akshare_client_maps_zt_pool(monkeypatch):
    """涨停池 DataFrame 映射为聚合器字段。"""
    client = AkshareSentimentClient()

    class FakeAk:
        @staticmethod
        def stock_zt_pool_em(*, date: str):
            assert date == "20240719"
            return pd.DataFrame(
                [
                    {
                        "代码": "000001",
                        "名称": "平安银行",
                        "连板数": 2,
                        "炸板次数": 0,
                        "封板资金": 1.5e8,
                        "所属行业": "银行",
                    }
                ]
            )

        @staticmethod
        def stock_zt_pool_dtgc_em(*, date: str):
            raise RuntimeError("no dt")

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAk())

    rows = client.fetch_limit_performance([], date(2024, 7, 19))
    assert len(rows) == 1
    assert rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["direct"] == 1
    assert rows[0]["sealCount"] == 2


def test_fallback_uses_secondary_when_primary_empty():
    """主源空列表时走次源。"""

    class Empty:
        def fetch_limit_performance(self, symbols, asof):
            return []

    class Secondary:
        def fetch_limit_performance(self, symbols, asof):
            return [{"symbol": "600000.SH", "direct": 1, "sealCount": 1, "breakUp": 0, "upAmount": 0}]

    rows = FallbackSentimentClient(Empty(), Secondary()).fetch_limit_performance([], date(2024, 1, 2))
    assert rows[0]["symbol"] == "600000.SH"
