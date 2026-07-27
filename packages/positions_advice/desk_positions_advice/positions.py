"""持仓读取与截断。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

MAX_POSITIONS = 20
logger = logging.getLogger(__name__)


def truncate_positions(
    positions: list[dict[str, Any]], *, limit: int = MAX_POSITIONS
) -> tuple[list[dict[str, Any]], bool]:
    """
    按市值降序截断；无市值则按 |浮盈|。

    @returns: (截断后列表, 是否截断)
    """
    if len(positions) <= limit:
        return list(positions), False

    def sort_key(p: dict[str, Any]) -> float:
        mv = p.get("market_value")
        if mv is not None:
            try:
                return float(mv)
            except (TypeError, ValueError):
                pass
        try:
            return abs(float(p.get("pnl") or 0))
        except (TypeError, ValueError):
            return 0.0

    ranked = sorted(positions, key=sort_key, reverse=True)
    return ranked[:limit], True


def _day_chg_pct_from_bars(db: Session, symbol: str, asof: date) -> float | None:
    """
    从日线计算 asof 当日涨跌幅（小数）；失败或数据不足返回 None。
    """
    try:
        from desk_market import MarketService

        start = asof - timedelta(days=20)
        df = MarketService(db).load_daily_df(symbol, start, asof)
        if df is None or getattr(df, "empty", True) or len(df) < 2:
            return None
        prev_close = float(df.iloc[-2]["close"])
        last_close = float(df.iloc[-1]["close"])
        if not prev_close:
            return None
        return round((last_close / prev_close) - 1.0, 6)
    except Exception:  # noqa: BLE001
        logger.debug("day_chg_pct unavailable for %s", symbol, exc_info=True)
        return None


def _auction_lookup(
    picks: list[dict[str, Any]] | None,
    context: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """从 picks / context 收集 symbol → auction_pct / auction_amount。"""
    out: dict[str, dict[str, Any]] = {}

    def ingest(rows: Any) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or row.get("code") or "").strip()
            if not sym:
                continue
            bucket = out.setdefault(sym, {})
            if "auction_pct" in row and row.get("auction_pct") is not None:
                bucket["auction_pct"] = row.get("auction_pct")
            if "auction_amount" in row and row.get("auction_amount") is not None:
                bucket["auction_amount"] = row.get("auction_amount")

    ingest(picks)
    if isinstance(context, dict):
        ingest(context.get("stocks"))
        ingest(context.get("picks"))
        # context 自身若带 symbol 字段则也尝试
        if context.get("symbol") or context.get("code"):
            ingest([context])
    return out


def enrich_positions(
    db: Session,
    positions: list[dict[str, Any]],
    *,
    asof: date,
    session_kind: str,
    picks: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    充实持仓事实：日涨跌幅；早盘再附竞价涨幅/额。

    日涨跌取数失败时字段保持 None，不抛错。
    """
    auction_map = (
        _auction_lookup(picks, context) if session_kind == "morning" else {}
    )
    enriched: list[dict[str, Any]] = []
    for raw in positions:
        p = dict(raw)
        sym = str(p.get("symbol") or "")
        if p.get("day_chg_pct") is None and sym:
            p["day_chg_pct"] = _day_chg_pct_from_bars(db, sym, asof)
        if session_kind == "morning" and sym:
            auc = auction_map.get(sym) or {}
            if "auction_pct" in auc and p.get("auction_pct") is None:
                p["auction_pct"] = auc["auction_pct"]
            if "auction_amount" in auc and p.get("auction_amount") is None:
                p["auction_amount"] = auc["auction_amount"]
        enriched.append(p)
    return enriched


def load_positions(db: Session, source: str) -> dict[str, Any]:
    """
    读取持仓。

    @param source: live | paper
    @returns: {ok, source, positions, error?, message?}
    """
    src = (source or "live").strip().lower()
    try:
        if src == "paper":
            from desk_broker import PaperBroker

            summary = PaperBroker(db).summary()
            positions = []
            for p in summary.get("positions") or []:
                if float(p.get("qty") or 0) <= 0:
                    continue
                qty = float(p["qty"])
                cost = float(p.get("cost") or 0)
                # paper summary 无现价时用成本近似市值
                last = float(p.get("last_price") or cost)
                mv = qty * last
                pnl = (last - cost) * qty
                positions.append(
                    {
                        "symbol": p["symbol"],
                        "qty": qty,
                        "cost": cost,
                        "last_price": last,
                        "market_value": mv,
                        "pnl": pnl,
                        "strategy_id": p.get("strategy_id"),
                    }
                )
            return {"ok": True, "source": "paper", "positions": positions, "message": None}
        # live：与 /api/broker/live/positions 一致
        from desk_broker import BrokerGateway

        snap = BrokerGateway(db).live.account_snapshot()
        positions = []
        for p in snap.get("positions") or []:
            if str(p.get("row_type") or "") == "sold":
                continue
            qty = float(p.get("qty") or 0)
            if qty <= 0:
                continue
            cost = float(p.get("cost") or 0)
            mv = p.get("market_value")
            if mv is None:
                last = float(p.get("last_price") or cost)
                mv = qty * last
            else:
                mv = float(mv)
                last = mv / qty if qty else cost
            pnl = (last - cost) * qty
            positions.append(
                {
                    "symbol": p["symbol"],
                    "qty": qty,
                    "cost": cost,
                    "last_price": last,
                    "market_value": mv,
                    "pnl": pnl,
                    "strategy_id": p.get("strategy_id"),
                }
            )
        return {
            "ok": True,
            "source": "live",
            "positions": positions,
            "message": snap.get("message"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "source": src,
            "positions": [],
            "error": str(exc),
            "message": str(exc),
        }
