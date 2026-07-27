"""持仓读取与截断。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

MAX_POSITIONS = 20


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
