"""research_source_label。"""

from desk_ai.source_label import research_source_label


def test_research_source_label_zh():
    assert research_source_label("morning") == "早盘"
    assert research_source_label("closing") == "尾盘"
    assert research_source_label("other") == "other"
