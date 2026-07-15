"""SentimentAggregator 单元测试。"""

from desk_sentiment.aggregator import aggregate_limit_rows


def test_aggregate_limit_rows_counts_and_rates():
    rows = [
        {
            "symbol": "000001.SZ",
            "name": "连板",
            "direct": 1,
            "sealCount": 3,
            "breakUp": 0,
            "upAmount": 1e8,
        },
        {
            "symbol": "600001.SH",
            "name": "破板",
            "direct": 1,
            "sealCount": 1,
            "breakUp": 2,
            "upAmount": 0,
        },
        {"symbol": "000002.SZ", "direct": 2, "sealCount": 1, "breakUp": 0},
    ]
    out = aggregate_limit_rows(rows)
    assert out["stat"]["limit_up_count"] == 2
    assert out["stat"]["limit_down_count"] == 1
    assert out["stat"]["max_board"] == 3
    assert out["stat"]["break_rate"] == 0.5
    assert out["stat"]["promote_rate"] == 0.5  # 1 sealed height>=2 / 2
    assert {s["symbol"]: s["status"] for s in out["stocks"]} == {
        "000001.SZ": "sealed",
        "600001.SH": "broken",
    }
