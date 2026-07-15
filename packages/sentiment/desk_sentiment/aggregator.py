"""涨停表现行 → 情绪统计与个股列表。"""

from __future__ import annotations

from typing import Any


def aggregate_limit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    聚合 limitupperformance 风格行。

    期望字段：symbol, name?, direct (1涨停/2跌停), sealCount, breakUp, upAmount

    @param rows: 原始行
    @returns: {"stat": {...}, "stocks": [...]}
    """
    up_rows: list[dict[str, Any]] = []
    down_count = 0
    for raw in rows:
        direct = int(raw.get("direct") or 0)
        if direct == 2:
            down_count += 1
            continue
        if direct != 1:
            continue
        height = int(raw.get("sealCount") or 1)
        broken = int(raw.get("breakUp") or 0) > 0
        up_rows.append(
            {
                "symbol": str(raw.get("symbol") or ""),
                "name": str(raw.get("name") or ""),
                "board_height": height,
                "seal_amount": float(raw.get("upAmount") or 0.0),
                "concept": str(raw.get("concept") or ""),
                "status": "broken" if broken else "sealed",
            }
        )

    limit_up = len(up_rows)
    broken_n = sum(1 for s in up_rows if s["status"] == "broken")
    promote_n = sum(
        1 for s in up_rows if s["board_height"] >= 2 and s["status"] == "sealed"
    )
    max_board = max((s["board_height"] for s in up_rows), default=0)
    break_rate = (broken_n / limit_up) if limit_up else 0.0
    promote_rate = (promote_n / limit_up) if limit_up else 0.0

    return {
        "stat": {
            "limit_up_count": limit_up,
            "limit_down_count": down_count,
            "max_board": max_board,
            "promote_rate": promote_rate,
            "break_rate": break_rate,
        },
        "stocks": up_rows,
    }
