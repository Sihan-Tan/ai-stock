"""实盘交易模式：纸面 / 审批 / 自动。"""

from __future__ import annotations

from desk_common.settings import Settings, get_settings


def live_execution_mode(settings: Settings | None = None) -> str:
    """
    返回 live 子模式。

    @returns: ``approval`` | ``auto`` | ``blocked``
    """
    s = settings or get_settings()
    if not s.auto_execute_live:
        return "approval"
    if not s.i_understand_auto_live:
        return "blocked"
    return "auto"


def auto_live_allowed(settings: Settings | None = None) -> bool:
    """是否允许自动实盘成交。"""
    return live_execution_mode(settings) == "auto"
