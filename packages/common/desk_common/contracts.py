"""跨包 Pydantic 合约。"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Signal(BaseModel):
    """策略信号。"""

    symbol: str
    side: Side
    strength: float = 1.0
    qty: float | None = None
    reason: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class OrderIntent(BaseModel):
    """下单意图。"""

    symbol: str
    side: Side
    qty: float
    price: float | None = None
    client_order_id: str
    strategy_id: str | None = None
    mode: Literal["paper", "live"] = "paper"


class OrderResult(BaseModel):
    """下单结果。"""

    client_order_id: str
    status: Literal["accepted", "filled", "rejected", "partial"]
    filled_qty: float = 0.0
    avg_price: float | None = None
    message: str = ""
    broker_order_id: str | None = None


class BacktestRequest(BaseModel):
    """回测请求。"""

    strategy_id: str
    symbol: str
    start: date
    end: date
    initial_cash: float = 1_000_000.0
    commission: float = 0.00025
    slippage: float = 0.001


class BacktestReport(BaseModel):
    """归一化回测报告。"""

    strategy_id: str
    symbol: str
    total_return: float
    max_drawdown: float
    sharpe: float | None = None
    trades: int = 0
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    trade_list: list[dict[str, Any]] = Field(default_factory=list)


class StrategySource(str, Enum):
    PYTHON = "python"
    YAML = "yaml"
    AGENT = "agent"


class StrategyMeta(BaseModel):
    """策略元数据。"""

    id: str
    name: str
    source: StrategySource
    version: str = "v0.1"
    status: Literal["draft", "research", "paper", "live", "archived"] = "research"
    entry_point: str | None = None
    yaml_body: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class StrongPickReport(BaseModel):
    """竞价后强势选拔结果。"""

    asof: date
    boards: list[dict[str, Any]] = Field(default_factory=list)
    stocks: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class MorningBrief(BaseModel):
    """晨会报告。"""

    asof: date
    stage: Literal["preopen", "post_auction"]
    content: str
    extras: dict[str, Any] = Field(default_factory=dict)
