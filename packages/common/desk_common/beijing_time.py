"""北京时间工具。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    """当前北京时间（带时区）。"""
    return datetime.now(BEIJING_TZ)


def beijing_today() -> date:
    """当前北京日历日。"""
    return beijing_now().date()
