"""东方财富板块客户端归类单测。"""

from __future__ import annotations

from desk_market.em_boards import EmBoardsClient


def test_classify_sector_and_precise_concepts():
    """行业字段 + 精选概念应分别归入 sector / concept。"""
    client = EmBoardsClient()
    boards = client._classify(
        industry="白酒",
        memberships=[
            {
                "BOARD_CODE": "438",
                "BOARD_NAME": "食品饮料",
                "BOARD_RANK": 1,
                "IS_PRECISE": "0",
            },
            {
                "BOARD_CODE": "1277",
                "BOARD_NAME": "白酒",
                "BOARD_RANK": 2,
                "IS_PRECISE": None,
            },
            {
                "BOARD_CODE": "500",
                "BOARD_NAME": "HS300_",
                "BOARD_RANK": 22,
                "IS_PRECISE": "0",
            },
            {
                "BOARD_CODE": "896",
                "BOARD_NAME": "高端品牌",
                "BOARD_RANK": 26,
                "IS_PRECISE": "1",
            },
            {
                "BOARD_CODE": "897",
                "BOARD_NAME": "白酒",
                "BOARD_RANK": 25,
                "IS_PRECISE": "1",
            },
        ],
    )
    by_type = {}
    for item in boards:
        by_type.setdefault(item["board_type"], []).append(item["board_name"])

    assert "白酒" in by_type["sector"]
    assert "食品饮料" in by_type["sector"]
    assert "高端品牌" in by_type["concept"]
    assert "白酒" in by_type["concept"]
    assert "HS300_" not in by_type.get("sector", [])
    assert "HS300_" not in by_type.get("concept", [])

    primary = {(b["board_type"], b["board_name"]) for b in boards if b.get("is_primary")}
    assert ("sector", "白酒") in primary
    assert ("concept", "白酒") in primary


def test_classify_without_industry_snapshot():
    """行业快照缺失时，仍能从 ssbk 前几级与精选概念归类。"""
    client = EmBoardsClient()
    boards = client._classify(
        industry=None,
        memberships=[
            {
                "BOARD_CODE": "438",
                "BOARD_NAME": "食品饮料",
                "BOARD_RANK": 1,
                "IS_PRECISE": "0",
            },
            {
                "BOARD_CODE": "1277",
                "BOARD_NAME": "白酒",
                "BOARD_RANK": 2,
                "IS_PRECISE": None,
            },
            {
                "BOARD_CODE": "1575",
                "BOARD_NAME": "白酒制造",
                "BOARD_RANK": 3,
                "IS_PRECISE": None,
            },
            {
                "BOARD_CODE": "896",
                "BOARD_NAME": "高端品牌",
                "BOARD_RANK": 26,
                "IS_PRECISE": "1",
            },
            {
                "BOARD_CODE": "1653",
                "BOARD_NAME": "味觉刺激",
                "BOARD_RANK": 23,
                "IS_PRECISE": "1",
            },
        ],
    )
    names = {(b["board_type"], b["board_name"]) for b in boards}
    assert ("sector", "食品饮料") in names
    assert ("sector", "白酒") in names
    assert ("concept", "高端品牌") in names

    primary = {b["board_name"]: b for b in boards if b.get("is_primary")}
    # 无快照时取行业链 rank 最大（最细分）
    assert primary["白酒制造"]["board_type"] == "sector"
    # 概念取 rank 最小的精选
    assert primary["味觉刺激"]["board_type"] == "concept"
