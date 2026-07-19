"""纸交易策略 Runner：复用回测同款 on_bar 上下文，信号转 Paper 订单。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.contracts import OrderIntent, Side
from desk_db.models import WatchlistItem
from desk_market import MarketService
from desk_strategy import StrategyRegistry
from desk_strategy.bar_context import build_bar_row


class PaperStrategyRunner:
    """
    对单标的跑一次策略评估并下纸单。

    口径对齐回测：用日线 history + ``build_bar_row``；买仅空仓、卖仅平仓；一 bar 最多一单。
    """

    def __init__(self, db: Session, *, account_name: str = "default"):
        # 延迟导入，避免与 desk_broker.__init__ 循环依赖
        from desk_broker import PaperBroker

        self.db = db
        self.broker = PaperBroker(db, account_name=account_name)
        self.registry = StrategyRegistry(db)

    def run_once(self, *, strategy_id: str, symbol: str) -> dict[str, Any]:
        """
        评估最新一根可用日 K 并尝试下单。

        @param strategy_id: 策略 ID
        @param symbol: 标的
        @returns: status / signals / orders / message
        """
        base: dict[str, Any] = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "signals": [],
            "orders": [],
            "last_price": None,
            "message": "",
        }
        reg = self.registry.load(strategy_id)
        if not reg or not reg.on_bar:
            base["status"] = "error"
            base["message"] = f"strategy not runnable: {strategy_id}"
            return base

        end = date.today()
        start = end - timedelta(days=400)
        df = MarketService(self.db).load_daily_df(symbol, start, end)
        if df is None or getattr(df, "empty", True) or len(df) < 30:
            base["status"] = "error"
            base["message"] = "insufficient bars"
            return base

        history = df.copy()
        idx = len(df) - 1
        lookback = min(250, idx + 1)
        slice_df = df.iloc[idx + 1 - lookback : idx + 1]
        row = build_bar_row(
            symbol,
            closes=slice_df["close"].astype(float).tolist(),
            highs=slice_df["high"].astype(float).tolist(),
            lows=slice_df["low"].astype(float).tolist(),
            opens=slice_df["open"].astype(float).tolist(),
            volumes=slice_df["volume"].astype(float).tolist(),
        )
        signals = reg.on_bar({"row": row, "history": history}) or []
        sig_dump = [
            s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in signals
        ]

        summary = self.broker.summary()
        held = {p["symbol"]: float(p["qty"]) for p in summary.get("positions") or []}
        last_price = float(df.iloc[-1]["close"])
        orders: list[dict[str, Any]] = []

        for sig in signals:
            side = sig.side if hasattr(sig, "side") else Side(str(sig["side"]))
            if side == Side.BUY and held.get(symbol, 0) > 0:
                continue
            if side == Side.SELL and held.get(symbol, 0) <= 0:
                continue
            qty = float(sig.qty) if getattr(sig, "qty", None) else None
            if qty is None or qty <= 0:
                if side == Side.BUY:
                    cash = float(summary["cash"])
                    qty = float(int((cash * 0.95) / last_price / 100) * 100)
                else:
                    qty = float(held.get(symbol, 0))
            if side == Side.BUY and qty < 100:
                continue
            if qty <= 0:
                continue
            intent = OrderIntent(
                symbol=symbol,
                side=side,
                qty=qty,
                price=last_price,
                client_order_id=f"paper|{strategy_id}|{symbol}|{uuid4().hex[:12]}",
                strategy_id=strategy_id,
                mode="paper",
            )
            result = self.broker.place_order(intent)
            orders.append(result.model_dump())
            break

        self.db.flush()
        base.update(
            {
                "status": "ok",
                "signals": sig_dump,
                "orders": orders,
                "last_price": last_price,
                "message": "",
            }
        )
        return base

    def run_watchlist(self, *, strategy_id: str) -> dict[str, Any]:
        """
        对自选全部标的各跑一次。

        @param strategy_id: 策略 ID
        @returns: 汇总与逐标的结果
        """
        symbols = list(
            self.db.scalars(select(WatchlistItem.symbol).order_by(WatchlistItem.symbol)).all()
        )
        results = [
            self.run_once(strategy_id=strategy_id, symbol=str(sym)) for sym in symbols
        ]
        filled = sum(
            1
            for r in results
            for o in r.get("orders") or []
            if o.get("status") == "filled"
        )
        return {
            "status": "ok",
            "strategy_id": strategy_id,
            "count": len(results),
            "filled": filled,
            "results": results,
        }
