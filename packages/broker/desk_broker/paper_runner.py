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

from desk_broker.promotion_gate import buy_block_reason, can_buy, max_capital_pct
from desk_strategy.factor_rules import get_rule_params


def _is_factor_rules_doc(parsed: Any) -> bool:
    """是否为 factor_rules YAML 文档。"""
    if not isinstance(parsed, dict):
        return False
    kind = str(parsed.get("kind") or "").strip().lower()
    if kind == "factor_rules":
        return True
    buy = parsed.get("buy")
    return isinstance(buy, dict) and "conditions" in buy


def _resolve_position_pct(parsed: dict[str, Any]) -> float | None:
    """
    解析 params.position_pct；None 表示走纸交易原默认口径。

    有值时钳制到 [1, 100]（与回测 sizer 一致）。
    """
    pos = get_rule_params(parsed).get("position_pct")
    if pos is None:
        return None
    return max(1.0, min(100.0, float(pos)))


def _bar_asof_date(df: Any) -> date:
    """最后一根 K 的交易日；解析失败则今天。"""
    try:
        raw = df.iloc[-1].get("date", df.iloc[-1].name)
    except Exception:  # noqa: BLE001
        return date.today()
    if hasattr(raw, "date"):
        return raw.date()
    if isinstance(raw, str) and len(raw) >= 10:
        return date.fromisoformat(raw[:10])
    return date.today()


def _count_trade_days_inclusive(db: Session, start: date, end: date) -> int:
    """含首尾的自然日区间内交易日个数。"""
    if start > end:
        return 0
    from desk_calendar import CalendarService

    cal = CalendarService(db)
    n = 0
    d = start
    while d <= end:
        if cal.is_trade_day(d):
            n += 1
        d += timedelta(days=1)
    return n


def _position_open_date_from_trades(
    db: Session, *, account_id: int, symbol: str
) -> date | None:
    """
    从 Paper 成交回放推断当前持仓的开仓日（无 opened_at 字段时的尽力方案）。
    """
    from desk_db.models import PaperTrade

    trades = db.scalars(
        select(PaperTrade)
        .where(PaperTrade.account_id == account_id, PaperTrade.symbol == symbol)
        .order_by(PaperTrade.id.asc())
    ).all()
    qty = 0.0
    open_at: date | None = None
    for t in trades:
        q = float(t.qty)
        side = str(t.side or "").lower()
        if side == "buy":
            if qty <= 1e-9:
                created = getattr(t, "created_at", None)
                if created is not None:
                    open_at = created.date() if hasattr(created, "date") else created
            qty += q
        elif side == "sell":
            qty -= q
            if qty <= 1e-9:
                qty = 0.0
                open_at = None
    return open_at if qty > 1e-9 else None


def _position_open_date(
    db: Session, broker: Any, *, symbol: str, summary_positions: list[dict[str, Any]]
) -> date | None:
    """
    持仓开仓日：PaperPosition/LivePosition 无 opened_at 时从成交推断。

    模型日后若增加 opened_at/created 可在此优先读取。
    """
    for p in summary_positions or []:
        if str(p.get("symbol")) != symbol:
            continue
        for key in ("opened_at", "open_date", "created_at"):
            raw = p.get(key)
            if raw is None:
                continue
            if isinstance(raw, date):
                return raw
            if isinstance(raw, str) and len(raw) >= 10:
                return date.fromisoformat(raw[:10])
            if hasattr(raw, "date"):
                return raw.date()
        break
    acc = broker._ensure_account()  # noqa: SLF001
    return _position_open_date_from_trades(db, account_id=int(acc.id), symbol=symbol)


def _buy_budget(
    *,
    parsed: dict[str, Any] | None,
    equity: float,
    cash: float,
    stage: str,
) -> float:
    """买入预算：factor_rules 可读 position_pct，仍受阶段 cap 与现金约束。"""
    cap = max_capital_pct(stage)
    pct = _resolve_position_pct(parsed) if parsed and _is_factor_rules_doc(parsed) else None
    if pct is not None:
        budget = equity * (pct / 100.0)
    else:
        budget = equity * cap if cap > 0 else cash * 0.95
    budget = min(budget, cash * 0.95)
    if cap > 0:
        budget = min(budget, equity * cap)
    return budget


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

        import yaml
        from desk_strategy.factor_rules import attach_ml_factor_columns, collect_factor_names

        body = getattr(reg.meta, "yaml_body", None) or ""
        parsed = yaml.safe_load(body) if body else None
        if isinstance(parsed, dict):
            history = attach_ml_factor_columns(
                history, collect_factor_names(parsed), self.db
            )

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

        summary = self.broker.summary()
        held = {p["symbol"]: float(p["qty"]) for p in summary.get("positions") or []}
        last_price = float(df.iloc[-1]["close"])
        asof = _bar_asof_date(df)
        notes: list[str] = []
        bars_held = 0
        rule_doc = parsed if isinstance(parsed, dict) and _is_factor_rules_doc(parsed) else None
        if rule_doc and float(held.get(symbol, 0)) > 0:
            max_hold = int(get_rule_params(rule_doc).get("max_hold_bars") or 0)
            if max_hold > 0:
                open_d = _position_open_date(
                    self.db,
                    self.broker,
                    symbol=symbol,
                    summary_positions=summary.get("positions") or [],
                )
                if open_d is None:
                    # PaperPosition 无开仓日字段且成交无法推断时跳过强制平仓
                    notes.append(
                        "max_hold_bars: no position open date; skipped force sell"
                    )
                else:
                    bars_held = _count_trade_days_inclusive(self.db, open_d, asof)

        signals = reg.on_bar(
            {"row": row, "history": history, "db": self.db, "bars_held": bars_held}
        ) or []
        sig_dump = [
            s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in signals
        ]

        orders: list[dict[str, Any]] = []
        stage = self._strategy_stage(strategy_id)
        gate_msg: str | None = None

        for sig in signals:
            side = sig.side if hasattr(sig, "side") else Side(str(sig["side"]))
            if side == Side.BUY and held.get(symbol, 0) > 0:
                continue
            if side == Side.SELL and held.get(symbol, 0) <= 0:
                continue
            if side == Side.BUY and not can_buy(stage):
                gate_msg = buy_block_reason(stage)
                reason = getattr(sig, "reason", "") or ""
                self._alert_paper(
                    title=f"纸交易·闸门拒绝买入 {symbol}",
                    body=(
                        f"策略 {strategy_id} · {symbol} · buy\n"
                        f"原因：{gate_msg}\n信号：{reason}"
                    ),
                    category="risk",
                    dedupe_key=f"reject:{strategy_id}:{symbol}:buy:{date.today().isoformat()}",
                )
                continue
            qty = float(sig.qty) if getattr(sig, "qty", None) else None
            if qty is None or qty <= 0:
                if side == Side.BUY:
                    budget = _buy_budget(
                        parsed=rule_doc,
                        equity=float(summary.get("equity") or summary["cash"]),
                        cash=float(summary["cash"]),
                        stage=stage,
                    )
                    qty = float(int(budget / last_price / 100) * 100)
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
            side_s = side.value if isinstance(side, Side) else str(side)
            asof = date.today().isoformat()
            if result.status in ("accepted", "filled", "partial"):
                self._alert_paper(
                    title=f"纸交易·{side_s.upper()} {symbol}",
                    body=(
                        f"策略 {strategy_id} · {symbol} · {side_s}\n"
                        f"数量 {qty:g} @ {last_price:g} · 状态 {result.status}\n"
                        f"{result.message or ''}".strip()
                    ),
                    category="paper",
                    dedupe_key=f"paper:{strategy_id}:{symbol}:{side_s}:{asof}",
                )
            elif result.status == "rejected":
                self._alert_paper(
                    title=f"纸交易·下单拒绝 {symbol}",
                    body=(
                        f"策略 {strategy_id} · {symbol} · {side_s}\n"
                        f"数量 {qty:g} · {result.message or 'rejected'}"
                    ),
                    category="risk",
                    dedupe_key=f"reject:{strategy_id}:{symbol}:{side_s}:{asof}",
                )
            break

        self.db.flush()
        message = gate_msg or ""
        if notes:
            base["notes"] = notes
        base.update(
            {
                "status": "ok",
                "signals": sig_dump,
                "orders": orders,
                "last_price": last_price,
                "lifecycle_stage": stage,
                "message": message,
            }
        )
        return base

    def _alert_paper(
        self, *, title: str, body: str, category: str, dedupe_key: str
    ) -> None:
        """发送飞书告警；失败不影响下单主路径。"""
        try:
            from desk_alert import FeishuWebhookChannel

            FeishuWebhookChannel(self.db).send(
                title, body, category=category, dedupe_key=dedupe_key
            )
        except Exception:  # noqa: BLE001
            pass

    def _strategy_stage(self, strategy_id: str) -> str:
        """读取策略生命周期阶段，缺省 incubating。"""
        from sqlalchemy import select

        from desk_db.models import StrategyRow

        row = self.db.scalar(
            select(StrategyRow)
            .where(StrategyRow.strategy_id == strategy_id)
            .order_by(StrategyRow.id.desc())
        )
        if row is None:
            return "incubating"
        return str(getattr(row, "lifecycle_stage", None) or "incubating")

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
