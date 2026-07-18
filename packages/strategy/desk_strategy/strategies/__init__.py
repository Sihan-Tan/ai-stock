"""策略子包：导入即注册到内存表。"""

from desk_strategy.strategies import (  # noqa: F401
    bias_revert,
    boll_revert,
    grid_classic,
    ma20_hold,
    ma_cross,
    macd_1d,
    multi_factor_lite,
    rsi_reversion,
    turtle_donchian,
)

__all__ = [
    "bias_revert",
    "boll_revert",
    "grid_classic",
    "ma20_hold",
    "ma_cross",
    "macd_1d",
    "multi_factor_lite",
    "rsi_reversion",
    "turtle_donchian",
]
