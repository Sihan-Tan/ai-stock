"""单标的详情：聚合、meta、板块、资金、技术面。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BoardMember, CapitalFlowDaily, SecurityMeta
from desk_indicators import compute

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_capital_client():
    """
    获取默认 AkShare 资金流客户端单例。

    将工厂放在本模块，便于 API 测试替换实时数据源。
    """
    from desk_market.akshare_capital import AkshareCapitalClient

    return AkshareCapitalClient()


@lru_cache(maxsize=1)
def get_boards_client():
    """
    获取默认东方财富板块客户端单例。

    将工厂放在本模块，便于 API 测试替换实时数据源。
    """
    from desk_market.em_boards import EmBoardsClient

    return EmBoardsClient()


def _f(v: Any) -> float | None:
    """
    将指标值转为 float；NaN / None → None。

    @param v: 原始标量
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def aggregate_ohlcv(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """
    将日线 OHLCV 聚合为周/月。

    @param df: 需含 date/open/high/low/close/volume/amount
    @param period: week | month
    """
    if df.empty:
        return df.copy()
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date")
    freq = "W-FRI" if period == "week" else "ME"
    grouped = out.set_index("date").resample(freq)
    agg = grouped.agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        }
    ).dropna(subset=["open"])
    agg = agg.reset_index()
    agg["date"] = agg["date"].dt.date
    return agg


def get_security_meta(db: Session, symbol: str) -> dict | None:
    """
    读取标的元数据。

    @param db: 数据库 Session
    @param symbol: 标的代码
    @returns: 元数据 dict，不存在则 None
    """
    sym = normalize_symbol(symbol)
    row = db.scalar(select(SecurityMeta).where(SecurityMeta.symbol == sym))
    if row is None:
        return None
    return {
        "symbol": row.symbol,
        "name": row.name,
        "is_delisted": row.is_delisted,
        "status": row.status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _board_point(row: BoardMember, *, is_primary: bool = False) -> dict:
    """
    将板块成分 ORM 行序列化为 API 结构。

    @param row: 板块成分行
    @param is_primary: 是否为该类型下最相关项
    """
    return {
        "board_code": row.board_code,
        "board_name": row.board_name,
        "board_type": row.board_type,
        "is_primary": is_primary,
    }


def list_boards_for_symbol(db: Session, symbol: str) -> list[dict]:
    """
    读取标的当前所属板块/概念；库空时东方财富 live 拉取并落库。

    @param db: 数据库 Session
    @param symbol: 标的代码
    @returns: 板块列表（仅 effective_to 为空的有效成分）
    """
    from desk_market.em_boards import annotate_primary_boards

    sym = normalize_symbol(symbol)
    rows = db.scalars(
        select(BoardMember).where(
            BoardMember.symbol == sym,
            BoardMember.effective_to.is_(None),
        )
    ).all()
    if rows:
        raw = [
            {
                "board_code": r.board_code,
                "board_name": r.board_name,
                "board_type": r.board_type,
            }
            for r in rows
        ]
        return annotate_primary_boards(raw)

    try:
        live_boards = get_boards_client().fetch(sym)
        if not live_boards:
            raise RuntimeError("boards client returned no data")
        today = date.today()
        for item in live_boards:
            board_code = str(item.get("board_code") or "").strip()
            board_name = str(item.get("board_name") or "").strip()
            board_type = str(item.get("board_type") or "concept").strip() or "concept"
            if not board_code or not board_name:
                continue
            existing = db.scalar(
                select(BoardMember).where(
                    BoardMember.symbol == sym,
                    BoardMember.board_code == board_code,
                    BoardMember.effective_to.is_(None),
                )
            )
            if existing:
                existing.board_name = board_name
                existing.board_type = board_type
            else:
                db.add(
                    BoardMember(
                        board_code=board_code,
                        board_name=board_name,
                        board_type=board_type,
                        symbol=sym,
                        effective_from=today,
                    )
                )
        db.commit()
    except Exception as exc:  # noqa: BLE001 — live 失败时返回空列表，由前端空态展示
        logger.warning("boards live fallback failed for %s: %s", sym, exc)
        db.rollback()
        return []

    persisted = db.scalars(
        select(BoardMember).where(
            BoardMember.symbol == sym,
            BoardMember.effective_to.is_(None),
        )
    ).all()
    raw = [
        {
            "board_code": r.board_code,
            "board_name": r.board_name,
            "board_type": r.board_type,
        }
        for r in persisted
    ]
    return annotate_primary_boards(raw)


def compute_technicals(db: Session, symbol: str, *, lookback_days: int = 180) -> dict:
    """
    基于库内日线计算 MA / MACD / RSI。

    @param db: 数据库 Session
    @param symbol: 标的代码
    @param lookback_days: 回溯自然日数
    @returns: available / latest / series 等字段
    """
    from desk_market import MarketService

    sym = normalize_symbol(symbol)
    to = date.today()
    fr = to - timedelta(days=lookback_days)
    df = MarketService(db).load_daily_df(sym, fr, to, adj=None)
    if df is None or df.empty or len(df) < 30:
        return {"available": False, "error": "insufficient bars", "symbol": sym}

    work = df.copy()
    if "date" not in work.columns and "ts" in work.columns:
        work = work.rename(columns={"ts": "date"})
    work = work.sort_values("date")
    ind = compute(work, ["SMA_5", "SMA_10", "SMA_20", "RSI_14", "MACD"])
    last = ind.iloc[-1]

    def _row_point(row: pd.Series) -> dict:
        d = row.get("date")
        return {
            "date": str(d)[:10] if d is not None else None,
            "ma5": _f(row.get("sma_5")),
            "ma10": _f(row.get("sma_10")),
            "ma20": _f(row.get("sma_20")),
            "macd": _f(row.get("macd")),
            "macd_signal": _f(row.get("macd_signal")),
            "macd_hist": _f(row.get("macd_hist")),
            "rsi14": _f(row.get("rsi_14")),
        }

    series = [_row_point(row) for _, row in ind.iterrows()]
    return {
        "available": True,
        "symbol": sym,
        "source": "db",
        "as_of": str(last.get("date", ""))[:10],
        "latest": {
            "ma5": _f(last.get("sma_5")),
            "ma10": _f(last.get("sma_10")),
            "ma20": _f(last.get("sma_20")),
            "macd": _f(last.get("macd")),
            "macd_signal": _f(last.get("macd_signal")),
            "macd_hist": _f(last.get("macd_hist")),
            "rsi14": _f(last.get("rsi_14")),
        },
        "series": series,
    }


_PERIOD_WINDOWS = (1, 3, 5, 10, 20)


def _capital_flow_point(row: CapitalFlowDaily) -> dict:
    """
    将资金流 ORM 行序列化为 API 数据点。

    @param row: 资金流日频行
    """
    return {
        "ts": row.ts.isoformat(),
        "main_net": float(row.main_net),
        "super_net": float(row.super_net),
        "large_net": float(row.large_net),
        "medium_net": float(row.medium_net),
        "small_net": float(row.small_net),
    }


def _sum_main_net_periods(series: list[dict[str, Any]]) -> dict[str, float | None]:
    """
    汇总主力净流入 N 日合计。

    @param series: 按时间升序的资金流序列
    """
    periods: dict[str, float | None] = {}
    for window in _PERIOD_WINDOWS:
        if len(series) < window:
            periods[str(window)] = None
            continue
        periods[str(window)] = float(sum(float(point["main_net"]) for point in series[-window:]))
    return periods


def _structure_from_live(live_rows: list[dict[str, Any]] | None) -> dict[str, float | None]:
    """
    从实时资金流行提取最新超大单/大单净占比。

    @param live_rows: 实时资金流行
    """
    if not live_rows:
        return {"super_pct": None, "large_pct": None}
    latest = live_rows[-1]
    return {
        "super_pct": latest.get("super_pct"),
        "large_pct": latest.get("large_pct"),
    }


def _persist_capital_rows(db: Session, sym: str, live_rows: list[dict[str, Any]]) -> None:
    """
    将实时资金流写入/更新库表。

    @param db: Session
    @param sym: 规范化 symbol
    @param live_rows: 实时行
    """
    for point in live_rows:
        ts = point["ts"]
        if not isinstance(ts, date):
            ts = pd.Timestamp(ts).date()
        existing = db.scalar(
            select(CapitalFlowDaily).where(
                CapitalFlowDaily.symbol == sym,
                CapitalFlowDaily.ts == ts,
            )
        )
        values = {
            key: float(point[key])
            for key in ("main_net", "super_net", "large_net", "medium_net", "small_net")
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(CapitalFlowDaily(symbol=sym, ts=ts, **values))
    db.commit()


def get_capital_flow(db: Session, symbol: str, *, days: int = 20) -> dict:
    """
    优先从库内读取个股资金流，缺失时 live 拉取并落库。

    额外附带 N 日主力净流入合计、当日超大单/大单净占比、融资余额。

    @param db: 数据库 Session
    @param symbol: 标的代码
    @param days: 返回的最大交易日数
    @returns: available/source/latest/periods/structure/margin/series 等字段
    """
    sym = normalize_symbol(symbol)
    need_days = max(days, max(_PERIOD_WINDOWS))
    client = get_capital_client()
    live_rows: list[dict[str, Any]] | None = None
    source = "db"

    rows = db.scalars(
        select(CapitalFlowDaily)
        .where(CapitalFlowDaily.symbol == sym)
        .order_by(CapitalFlowDaily.ts.desc())
        .limit(need_days)
    ).all()

    if not rows:
        try:
            live_rows = client.fetch_daily(sym, days=need_days)
            if not live_rows:
                raise RuntimeError("capital flow client returned no data")
            _persist_capital_rows(db, sym, live_rows)
            source = "live"
            rows = db.scalars(
                select(CapitalFlowDaily)
                .where(CapitalFlowDaily.symbol == sym)
                .order_by(CapitalFlowDaily.ts.desc())
                .limit(need_days)
            ).all()
        except Exception as exc:  # noqa: BLE001 — 实时源失败需降级为可用性响应
            db.rollback()
            return {"available": False, "error": str(exc)[:200], "symbol": sym}

    series = [_capital_flow_point(row) for row in reversed(rows)]
    if not series:
        return {"available": False, "error": "capital flow persistence failed", "symbol": sym}

    structure = _structure_from_live(live_rows)
    if structure.get("super_pct") is None and structure.get("large_pct") is None:
        try:
            peek = client.fetch_daily(sym, days=min(5, need_days))
            structure = _structure_from_live(peek)
        except Exception as exc:  # noqa: BLE001
            logger.debug("capital structure peek failed for %s: %s", sym, exc)

    margin: dict[str, Any] | None = None
    try:
        margin = client.fetch_margin(sym)
    except Exception as exc:  # noqa: BLE001
        logger.debug("margin fetch failed for %s: %s", sym, exc)

    latest = {key: series[-1][key] for key in series[-1] if key != "ts"}
    if structure.get("super_pct") is not None:
        latest["super_pct"] = structure["super_pct"]
    if structure.get("large_pct") is not None:
        latest["large_pct"] = structure["large_pct"]

    return {
        "available": True,
        "symbol": sym,
        "source": source,
        "as_of": series[-1]["ts"],
        "latest": latest,
        "periods": _sum_main_net_periods(series),
        "structure": structure,
        "margin": margin,
        "series": series,
    }
