"""ORM 模型（行情 / 日历 / 情绪 / 龙虎榜 / 策略 / 模拟盘 / 实盘 / 告警 / 复盘 / ML / 知识库 / 晨会）。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from desk_db import Base

# 价格字段：库内固定三位小数
Price3 = Numeric(18, 3)


class BarDaily(Base):
    __tablename__ = "bars_daily"
    __table_args__ = (UniqueConstraint("symbol", "ts", name="uq_bars_daily_symbol_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Price3)
    high: Mapped[float] = mapped_column(Price3)
    low: Mapped[float] = mapped_column(Price3)
    close: Mapped[float] = mapped_column(Price3)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    adj_factor: Mapped[float] = mapped_column(Float, default=1.0)
    open_hfq: Mapped[float | None] = mapped_column(Price3, nullable=True)
    high_hfq: Mapped[float | None] = mapped_column(Price3, nullable=True)
    low_hfq: Mapped[float | None] = mapped_column(Price3, nullable=True)
    close_hfq: Mapped[float | None] = mapped_column(Price3, nullable=True)
    volume_hfq: Mapped[float | None] = mapped_column(Float, nullable=True)


class SecurityMeta(Base):
    """标的元数据（退市状态等）。"""

    __tablename__ = "security_meta"
    __table_args__ = (UniqueConstraint("symbol", name="uq_security_meta_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    is_delisted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="listed")  # listed|delisted|...
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketJobRun(Base):
    """行情同步任务运行记录。"""

    __tablename__ = "market_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ok|failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    symbols_done: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")


class BarMinute(Base):
    __tablename__ = "bars_minute"
    __table_args__ = (UniqueConstraint("symbol", "ts", name="uq_bars_minute_symbol_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Price3)
    high: Mapped[float] = mapped_column(Price3)
    low: Mapped[float] = mapped_column(Price3)
    close: Mapped[float] = mapped_column(Price3)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)


class QuoteSnapshot(Base):
    __tablename__ = "quotes_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    last: Mapped[float] = mapped_column(Price3, default=0.0)
    pct_chg: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BoardMember(Base):
    __tablename__ = "board_members"
    __table_args__ = (
        UniqueConstraint("board_code", "symbol", "effective_from", name="uq_board_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_code: Mapped[str] = mapped_column(String(32), index=True)
    board_name: Mapped[str] = mapped_column(String(64), default="")
    board_type: Mapped[str] = mapped_column(String(16), default="concept")  # sector|concept|index
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class CapitalFlowDaily(Base):
    """个股资金流向日频（可选落库）。"""

    __tablename__ = "capital_flow_daily"
    __table_args__ = (UniqueConstraint("symbol", "ts", name="uq_capital_flow_daily_symbol_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    ts: Mapped[date] = mapped_column(Date, index=True)
    main_net: Mapped[float] = mapped_column(Float, default=0.0)
    super_net: Mapped[float] = mapped_column(Float, default=0.0)
    large_net: Mapped[float] = mapped_column(Float, default=0.0)
    medium_net: Mapped[float] = mapped_column(Float, default=0.0)
    small_net: Mapped[float] = mapped_column(Float, default=0.0)


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("symbol", name="uq_watchlist_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TradeCalendar(Base):
    __tablename__ = "trade_calendar"
    __table_args__ = (UniqueConstraint("cal_date", name="uq_trade_calendar_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cal_date: Mapped[date] = mapped_column(Date, index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(64), default="")


class SuspensionEvent(Base):
    __tablename__ = "suspension_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    event_type: Mapped[str] = mapped_column(String(16))  # suspend|resume
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    scope: Mapped[str] = mapped_column(String(32), default="watchlist")


class CalendarEvent(Base):
    """财经日历 / 重大新闻 / 相关催化剂。"""

    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_calendar_events_source_ext"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_time: Mapped[str] = mapped_column(String(16), default="")
    category: Mapped[str] = mapped_column(String(32), default="macro", index=True)
    """news|macro|earnings|lockup|ipo|catalyst"""
    importance: Mapped[int] = mapped_column(Integer, default=3)
    """1–5，越高越重大。"""
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    symbol: Mapped[str] = mapped_column(String(16), default="")
    name: Mapped[str] = mapped_column(String(64), default="")
    region: Mapped[str] = mapped_column(String(16), default="CN")
    source: Mapped[str] = mapped_column(String(32), default="seed")
    external_id: Mapped[str] = mapped_column(String(128), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LimitUpStat(Base):
    __tablename__ = "limit_up_stats"
    __table_args__ = (UniqueConstraint("asof", name="uq_limit_up_stats_asof"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    limit_up_count: Mapped[int] = mapped_column(Integer, default=0)
    limit_down_count: Mapped[int] = mapped_column(Integer, default=0)
    max_board: Mapped[int] = mapped_column(Integer, default=0)
    promote_rate: Mapped[float] = mapped_column(Float, default=0.0)
    break_rate: Mapped[float] = mapped_column(Float, default=0.0)


class LimitUpStock(Base):
    __tablename__ = "limit_up_stocks"
    __table_args__ = (Index("ix_limit_up_stocks_asof", "asof"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date)
    symbol: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64), default="")
    board_height: Mapped[int] = mapped_column(Integer, default=1)
    seal_amount: Mapped[float] = mapped_column(Float, default=0.0)
    concept: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="sealed")  # sealed|broken


class LhbDaily(Base):
    __tablename__ = "lhb_daily"
    __table_args__ = (Index("ix_lhb_daily_asof", "asof"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(128), default="")
    net_buy: Mapped[float] = mapped_column(Float, default=0.0)


class LhbSeat(Base):
    __tablename__ = "lhb_seats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lhb_id: Mapped[int] = mapped_column(Integer, index=True)
    side: Mapped[str] = mapped_column(String(8))  # buy|sell
    seat_name: Mapped[str] = mapped_column(String(128))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    is_institution: Mapped[bool] = mapped_column(Boolean, default=False)


class StrategyRow(Base):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_id_ver"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16))  # python|yaml|agent
    version: Mapped[str] = mapped_column(String(32), default="v0.1")
    status: Mapped[str] = mapped_column(String(16), default="research")
    """兼容字段：draft|research|paper|live|archived。"""
    lifecycle_stage: Mapped[str] = mapped_column(String(16), default="incubating")
    """incubating|paper|probation|production|retired。"""
    description: Mapped[str] = mapped_column(String(256), default="")
    capital_pct: Mapped[float] = mapped_column(Float, default=0.0)
    capital_allocated: Mapped[float] = mapped_column(Float, default=0.0)
    kpi_json: Mapped[str] = mapped_column(Text, default="{}")
    lifecycle_history_json: Mapped[str] = mapped_column(Text, default="[]")
    entry_point: Mapped[str | None] = mapped_column(String(256), nullable=True)
    yaml_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lifecycle_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    total_return: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    trades: Mapped[int] = mapped_column(Integer, default=0)
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), default="default", unique=True)
    cash: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_paper_pos"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="accepted")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    client_order_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CashLedger(Base):
    __tablename__ = "cash_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    delta: Mapped[float] = mapped_column(Float)
    balance: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LiveOrder(Base):
    __tablename__ = "live_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="accepted")
    message: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LivePosition(Base):
    __tablename__ = "live_positions"
    __table_args__ = (UniqueConstraint("symbol", name="uq_live_pos_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16))
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BrokerFill(Base):
    __tablename__ = "broker_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertRow(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), default="feishu")
    category: Mapped[str] = mapped_column(String(32), default="signal")
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(128), index=True, default="")
    status: Mapped[str] = mapped_column(String(16), default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReviewNote(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    deviations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MlModel(Base):
    __tablename__ = "ml_models"
    __table_args__ = (UniqueConstraint("model_id", name="uq_ml_model_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    engine: Mapped[str] = mapped_column(String(16))  # lightgbm|xgboost
    path: Mapped[str] = mapped_column(String(256))
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    features_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    doc_type: Mapped[str] = mapped_column(String(32), default="markdown")
    tags: Mapped[str] = mapped_column(String(256), default="")
    path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)


class MorningBriefRow(Base):
    __tablename__ = "morning_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    stage: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    extras_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuctionSnapshot(Base):
    __tablename__ = "auction_snapshots"
    __table_args__ = (UniqueConstraint("asof", "symbol", name="uq_auction_asof_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    auction_pct: Mapped[float] = mapped_column(Float, default=0.0)
    auction_amount: Mapped[float] = mapped_column(Float, default=0.0)
    board_code: Mapped[str] = mapped_column(String(32), default="")
    board_name: Mapped[str] = mapped_column(String(64), default="")


class MorningStrongPick(Base):
    __tablename__ = "morning_strong_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asof: Mapped[date] = mapped_column(Date, index=True)
    pick_type: Mapped[str] = mapped_column(String(16))  # board|stock
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")


class FinancialSnapshot(Base):
    """财务快照缓存（投研）。"""

    __tablename__ = "financial_snapshots"
    __table_args__ = (
        UniqueConstraint("symbol", "table_name", "period", name="uq_financial_snap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    table_name: Mapped[str] = mapped_column(String(32))  # Balance|Income|CashFlow|Pershareindex|Capital|Abstract
    period: Mapped[str] = mapped_column(String(16))  # YYYYMMDD 报告期
    source: Mapped[str] = mapped_column(String(16))  # qmt|akshare
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
