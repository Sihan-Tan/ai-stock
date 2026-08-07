"""投研精选表格 PNG。"""

from __future__ import annotations

from datetime import date

from desk_common.contracts import ResearchPickItem
from desk_ai.research_table_image import render_research_table_png, wrap_rationale_lines


def test_wrap_rationale_max_three_lines():
    lines = wrap_rationale_lines("一" * 200, max_chars_per_line=12, max_lines=3)
    assert len(lines) <= 3
    assert lines[-1].endswith("…") or len("".join(lines)) <= 36


def test_render_png_header_and_bytes():
    picks = [
        ResearchPickItem(
            rank=1,
            symbol="600519.SH",
            name="贵州茅台",
            score=90,
            confidence=88,
            buy_low=1600,
            buy_high=1650,
            target_low=1700,
            target_high=1800,
            stop_loss=1550,
            rationale="强势" + "理由" * 40,
        )
    ]
    raw = render_research_table_png(date(2026, 8, 7), "morning", picks)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 500
