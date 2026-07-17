"""竞价分钟缺口：tick 聚合补 09:15–09:29。"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import pytest

from desk_market.qmt_md import MockQmtMarketData, XtdataMarketData


def test_get_minute_bars_fills_auction_from_ticks() -> None:
    """缺失的竞价分钟应由同分钟 tick 聚合补齐。"""
    md = MockQmtMarketData()
    md.seed_minute(
        "600519.SH",
        datetime(2026, 7, 15, 9, 30, 0),
        open=10,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=100,
        amount=1010,
    )
    md.seed_ticks(
        "600519.SH",
        [
            {
                "ts": datetime(2026, 7, 15, 9, 15, 10),
                "last": 9.8,
                "volume": 10,
                "amount": 98,
            },
            {
                "ts": datetime(2026, 7, 15, 9, 15, 40),
                "last": 9.9,
                "volume": 20,
                "amount": 198,
            },
            {
                "ts": datetime(2026, 7, 15, 9, 20, 5),
                "last": 10.0,
                "volume": 5,
                "amount": 50,
            },
        ],
    )

    df = md.get_minute_bars(
        "600519.SH", "2026-07-15 09:15:00", "2026-07-15 09:35:00"
    )

    assert not df.empty
    minutes = {pd.Timestamp(ts).strftime("%H:%M") for ts in df["ts"]}
    assert {"09:15", "09:20", "09:30"} <= minutes
    assert "09:16" not in minutes
    row_915 = df[
        df["ts"].map(
            lambda ts: pd.Timestamp(ts).hour == 9 and pd.Timestamp(ts).minute == 15
        )
    ].iloc[0]
    assert float(row_915["open"]) == 9.8
    assert float(row_915["close"]) == 9.9
    assert float(row_915["high"]) == 9.9
    assert float(row_915["low"]) == 9.8


def test_get_minute_bars_keeps_existing_auction_minute() -> None:
    """已有 1m 竞价分钟不被 tick 聚合覆盖。"""
    md = MockQmtMarketData()
    md.seed_minute(
        "600519.SH",
        datetime(2026, 7, 15, 9, 15, 0),
        open=9.5,
        high=9.6,
        low=9.4,
        close=9.55,
        volume=50,
        amount=477,
    )
    md.seed_minute(
        "600519.SH",
        datetime(2026, 7, 15, 9, 30, 0),
        open=10,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=100,
        amount=1010,
    )
    md.seed_ticks(
        "600519.SH",
        [
            {
                "ts": datetime(2026, 7, 15, 9, 15, 10),
                "last": 9.8,
                "volume": 10,
                "amount": 98,
            },
            {
                "ts": datetime(2026, 7, 15, 9, 15, 40),
                "last": 9.9,
                "volume": 20,
                "amount": 198,
            },
        ],
    )

    df = md.get_minute_bars(
        "600519.SH", "2026-07-15 09:15:00", "2026-07-15 09:35:00"
    )

    row_915 = df[
        df["ts"].map(
            lambda ts: pd.Timestamp(ts).hour == 9 and pd.Timestamp(ts).minute == 15
        )
    ].iloc[0]
    assert float(row_915["open"]) == 9.5
    assert float(row_915["close"]) == 9.55
    assert float(row_915["high"]) == 9.6
    assert float(row_915["low"]) == 9.4
    assert float(row_915["volume"]) == 50


def test_ensure_auction_minutes_returns_original_on_tick_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """tick 下载失败时保留原分钟数据并记录 warning。"""
    md = object.__new__(XtdataMarketData)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    md._xt = type(
        "XT",
        (),
        {
            "download_history_data": staticmethod(_boom),
            "get_market_data_ex": staticmethod(lambda *_a, **_k: {}),
        },
    )()
    original = pd.DataFrame(
        [
            {
                "ts": datetime(2026, 7, 15, 9, 30, 0),
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 100.0,
                "amount": 1010.0,
            }
        ]
    )

    with caplog.at_level(logging.WARNING):
        out = md._ensure_auction_minutes(
            "600519.SH",
            original,
            datetime(2026, 7, 15, 9, 15),
            datetime(2026, 7, 15, 9, 35),
        )

    assert len(out) == len(original)
    pd.testing.assert_frame_equal(out, original)
    assert any(
        "tick" in record.message.lower() or "auction" in record.message.lower()
        for record in caplog.records
    )
