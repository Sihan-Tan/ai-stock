"""BrokerGateway：Paper / MockQMT / RiskGate。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.contracts import OrderIntent, OrderResult, Side
from desk_common.settings import get_settings
from desk_common.trading_cost import apply_slippage, calc_buy_commission, calc_sell_fees
from desk_db.models import (
    BarDaily,
    BrokerFill,
    CashLedger,
    LiveOrder,
    LivePosition,
    PaperAccount,
    PaperOrder,
    PaperPosition,
    PaperTrade,
    QuoteSnapshot,
)


class Broker(Protocol):
    def place_order(self, intent: OrderIntent) -> OrderResult: ...


class PaperBroker:
    """模拟盘：全部持久化。"""

    def __init__(self, db: Session, account_name: str = "default"):
        self.db = db
        self.account_name = account_name
        self._ensure_account()

    def _ensure_account(self) -> PaperAccount:
        acc = self.db.scalar(select(PaperAccount).where(PaperAccount.name == self.account_name))
        if not acc:
            cash = get_settings().paper_initial_cash
            acc = PaperAccount(name=self.account_name, cash=cash, equity=cash)
            self.db.add(acc)
            self.db.flush()
            self.db.add(
                CashLedger(account_id=acc.id, delta=cash, balance=cash, reason="init")
            )
            self.db.flush()
        return acc

    def _last_price(self, symbol: str, *, fallback: float | None = None) -> float | None:
        """快照价 → 最近日线收盘 → fallback。"""
        snap = self.db.scalar(
            select(QuoteSnapshot).where(QuoteSnapshot.symbol == symbol)
        )
        if snap is not None and float(snap.last) > 0:
            return float(snap.last)
        bar = self.db.scalar(
            select(BarDaily)
            .where(BarDaily.symbol == symbol)
            .order_by(BarDaily.ts.desc())
            .limit(1)
        )
        if bar is not None and float(bar.close) > 0:
            return float(bar.close)
        return fallback

    def _mark_equity(self, acc: PaperAccount) -> float:
        """现金 + 持仓市值。"""
        positions = self.db.scalars(
            select(PaperPosition).where(PaperPosition.account_id == acc.id)
        ).all()
        equity = float(acc.cash)
        for p in positions:
            last = self._last_price(p.symbol, fallback=float(p.cost)) or float(p.cost)
            equity += float(p.qty) * last
        acc.equity = equity
        return equity

    def summary(self) -> dict:
        """账户摘要（含近期成交）；权益含持仓市值。"""
        acc = self._ensure_account()
        positions = self.db.scalars(
            select(PaperPosition).where(PaperPosition.account_id == acc.id)
        ).all()
        self._mark_equity(acc)
        trades = self.db.scalars(
            select(PaperTrade)
            .where(PaperTrade.account_id == acc.id)
            .order_by(PaperTrade.id.desc())
            .limit(50)
        ).all()
        settings = get_settings()
        self.db.flush()
        return {
            "cash": acc.cash,
            "equity": acc.equity,
            "initial_cash": settings.paper_initial_cash,
            "account": acc.name,
            "updated_at": acc.updated_at.isoformat() if acc.updated_at else None,
            "positions": [
                {"symbol": p.symbol, "qty": p.qty, "cost": p.cost} for p in positions
            ],
            "trades": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "qty": t.qty,
                    "price": t.price,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in trades
            ],
        }

    def reset_account(self) -> dict:
        """重置持仓与成交，恢复初始资金。"""
        acc = self._ensure_account()
        for p in self.db.scalars(
            select(PaperPosition).where(PaperPosition.account_id == acc.id)
        ).all():
            self.db.delete(p)
        for t in self.db.scalars(
            select(PaperTrade).where(PaperTrade.account_id == acc.id)
        ).all():
            self.db.delete(t)
        for o in self.db.scalars(
            select(PaperOrder).where(PaperOrder.account_id == acc.id)
        ).all():
            self.db.delete(o)
        cash = get_settings().paper_initial_cash
        acc.cash = cash
        acc.equity = cash
        acc.updated_at = datetime.utcnow()
        self.db.add(
            CashLedger(account_id=acc.id, delta=cash, balance=cash, reason="reset")
        )
        self.db.flush()
        return self.summary()


    def place_order(self, intent: OrderIntent) -> OrderResult:
        """
        以指定价成交，扣 A 股费用（与回测同公式），权益含持仓市值。
        """
        acc = self._ensure_account()
        raw = intent.price if intent.price is not None else 0.0
        if raw <= 0:
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="rejected",
                message="price required for paper fill",
            )
        fee = get_settings()
        price = apply_slippage(
            float(raw),
            intent.side.value,
            slippage=float(fee.backtest_slippage or 0.0),
        )
        notional = price * intent.qty
        pos = self.db.scalar(
            select(PaperPosition).where(
                PaperPosition.account_id == acc.id, PaperPosition.symbol == intent.symbol
            )
        )
        if intent.side == Side.BUY:
            commission = calc_buy_commission(
                notional,
                buy_commission=fee.backtest_buy_commission,
                min_commission=fee.backtest_min_commission,
            )
            stamp = 0.0
            cash_delta = -(notional + commission)
            if notional + commission > acc.cash:
                return OrderResult(
                    client_order_id=intent.client_order_id,
                    status="rejected",
                    message="insufficient cash",
                )
        else:
            if not pos or pos.qty < intent.qty:
                return OrderResult(
                    client_order_id=intent.client_order_id,
                    status="rejected",
                    message="insufficient position",
                )
            commission, stamp = calc_sell_fees(
                notional,
                sell_commission=fee.backtest_sell_commission,
                stamp_duty=fee.backtest_stamp_duty,
                min_commission=fee.backtest_min_commission,
            )
            cash_delta = notional - commission - stamp

        self.db.add(
            PaperOrder(
                account_id=acc.id,
                client_order_id=intent.client_order_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=price,
                status="filled",
            )
        )
        self.db.add(
            PaperTrade(
                account_id=acc.id,
                client_order_id=intent.client_order_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=price,
            )
        )
        if intent.side == Side.BUY:
            acc.cash += cash_delta
            if not pos:
                self.db.add(
                    PaperPosition(
                        account_id=acc.id, symbol=intent.symbol, qty=intent.qty, cost=price
                    )
                )
            else:
                new_qty = pos.qty + intent.qty
                pos.cost = (pos.cost * pos.qty + price * intent.qty) / new_qty
                pos.qty = new_qty
        else:
            acc.cash += cash_delta
            pos.qty -= intent.qty
            if pos.qty <= 0:
                self.db.delete(pos)
        acc.updated_at = datetime.utcnow()
        self._mark_equity(acc)
        fee_total = commission + stamp
        self.db.add(
            CashLedger(
                account_id=acc.id,
                delta=cash_delta,
                balance=acc.cash,
                reason=f"fill:{intent.client_order_id};fee={fee_total:.4f}",
            )
        )
        self.db.flush()
        return OrderResult(
            client_order_id=intent.client_order_id,
            status="filled",
            filled_qty=intent.qty,
            avg_price=price,
            message=f"paper filled; fee={fee_total:.2f}",
        )


@dataclass
class RiskGate:
    """实盘风控闸门。"""

    armed: bool = False
    kill_switch: bool = False
    max_order_position_pct: float = 10.0
    max_order_notional: float = 50_000.0
    max_daily_notional: float = 200_000.0
    whitelist: set[str] = field(default_factory=set)
    daily_used: float = 0.0

    def check_size_limits(
        self, intent: OrderIntent, *, equity: float | None = None
    ) -> str | None:
        """
        仓位/金额限额（模拟与实盘均适用）。

        单笔上限取「权益×仓位百分比」与「单笔最大金额」的较小者；
        另受单日累计金额限制。

        @param equity: 账户总权益；缺失时仅按单笔最大金额校验
        """
        if not intent.price:
            return None
        notional = float(intent.price) * float(intent.qty)
        caps: list[float] = [float(self.max_order_notional)]
        if equity is not None and equity > 0:
            caps.append(float(equity) * (float(self.max_order_position_pct) / 100.0))
        single_cap = min(caps)
        if notional > single_cap + 1e-6:
            return "exceeds single order cap (min of position% and notional)"
        if self.daily_used + notional > self.max_daily_notional:
            return "exceeds daily limit"
        return None

    def check_live_gates(self, intent: OrderIntent) -> str | None:
        """实盘闸门：Kill / ARM / 白名单（不含金额仓位限额）。"""
        if self.kill_switch:
            return "kill switch active"
        if not self.armed:
            return "live not armed"
        if self.whitelist and intent.symbol not in self.whitelist:
            return "symbol not in whitelist"
        return None

    def check(self, intent: OrderIntent, *, equity: float | None = None) -> str | None:
        """实盘完整校验：闸门 + 设置页下单限额。"""
        gate = self.check_live_gates(intent)
        if gate:
            return gate
        return self.check_size_limits(intent, equity=equity)

    def apply_from_settings(self) -> None:
        """从 Settings（.env / 设置页）同步限额字段，作为唯一来源。"""
        settings = get_settings()
        self.max_order_position_pct = float(settings.risk_max_order_position_pct)
        self.max_order_notional = float(settings.risk_max_order_notional)
        self.max_daily_notional = float(settings.risk_max_daily_notional)


class MockQmtBroker:
    """无 miniQMT 时的模拟柜台（仍写入 live 表以演示流程）。"""

    def __init__(self, db: Session):
        self.db = db
        self.connected = True
        self.mode = "mock"

    def ping(self) -> dict:
        """连通探测。"""
        settings = get_settings()
        return {
            "connected": self.connected,
            "mode": self.mode,
            "userdata": settings.qmt_userdata_path,
            "account_id": settings.qmt_account_id or "mock",
        }

    def place_order(self, intent: OrderIntent) -> OrderResult:
        """模拟成交。"""
        price = intent.price or 0.0
        self.db.add(
            LiveOrder(
                client_order_id=intent.client_order_id,
                broker_order_id=f"MOCK-{uuid4().hex[:8]}",
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=price,
                status="filled",
                message="mock qmt fill",
            )
        )
        self.db.add(
            BrokerFill(
                client_order_id=intent.client_order_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=price,
            )
        )
        pos = self.db.scalar(select(LivePosition).where(LivePosition.symbol == intent.symbol))
        if intent.side == Side.BUY:
            if not pos:
                self.db.add(LivePosition(symbol=intent.symbol, qty=intent.qty, cost=price))
            else:
                new_qty = pos.qty + intent.qty
                pos.cost = (pos.cost * pos.qty + price * intent.qty) / max(new_qty, 1e-9)
                pos.qty = new_qty
        elif pos:
            pos.qty = max(0.0, pos.qty - intent.qty)
        self.db.flush()
        return OrderResult(
            client_order_id=intent.client_order_id,
            status="filled",
            filled_qty=intent.qty,
            avg_price=price,
            broker_order_id=f"MOCK-{intent.client_order_id[:8]}",
            message="mock qmt fill",
        )


class QmtBroker(MockQmtBroker):
    """
    miniQMT 适配：探测 xtquant；不可用时自动降级 Mock。

    真实下单仅在安装 xtquant 且 ARM 通过后走通；本类保证演示路径可测。
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self._xt = None
        try:
            import xtquant.xttrader  # type: ignore  # noqa: F401

            self._xt = True
            self.mode = "qmt"
            self.connected = True
        except Exception:  # noqa: BLE001
            self._xt = None
            self.mode = "mock"
            self.connected = True

    def place_order(self, intent: OrderIntent) -> OrderResult:
        """
        自动实盘成交。

        已装 xtquant 且 ``AUTO_EXECUTE_LIVE``+确认变量开启时仍默认 Mock 落库，
        避免无柜台环境误发真单；message 标明 mode，后续可在此接 XtQuantTrader。
        """
        from desk_broker.trading_mode import auto_live_allowed

        if not auto_live_allowed():
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="rejected",
                message="auto live blocked: set AUTO_EXECUTE_LIVE=1 and I_UNDERSTAND_AUTO_LIVE=1",
            )
        result = super().place_order(intent)
        if self._xt:
            result.message = (result.message or "") + "; xtquant detected (mock fill; wire trader for real)"
        return result


class BrokerGateway:
    """统一网关。"""

    def __init__(self, db: Session):
        self.db = db
        self.paper = PaperBroker(db)
        self.live = QmtBroker(db)
        self.risk = RiskGate(whitelist=set())
        self.risk.apply_from_settings()

    def _paper_equity(self) -> float:
        """模拟账户权益。"""
        acc = self.paper._ensure_account()
        return float(acc.equity or 0.0)

    def _live_equity_estimate(self) -> float:
        """实盘权益近似：持仓成本市值，至少不低于模拟初始资金。"""
        positions = self.db.scalars(select(LivePosition)).all()
        pos_val = sum(float(p.cost) * float(p.qty) for p in positions)
        floor = float(get_settings().paper_initial_cash)
        return max(pos_val, floor)

    def place_order(self, intent: OrderIntent) -> OrderResult:
        """
        按 mode 路由。

        设置页「下单限额」每次下单前从 Settings 同步，对 **模拟与实盘** 均强制生效；
        实盘额外要求 Kill/ARM/白名单。
        """
        # 限额以设置/.env 为准，避免被风控页内存值覆盖后长期偏离
        self.risk.apply_from_settings()
        equity = (
            self._paper_equity()
            if intent.mode == "paper"
            else self._live_equity_estimate()
        )
        limit_reason = self.risk.check_size_limits(intent, equity=equity)
        if limit_reason:
            if intent.mode != "paper":
                self.db.add(
                    LiveOrder(
                        client_order_id=intent.client_order_id,
                        symbol=intent.symbol,
                        side=intent.side.value,
                        qty=intent.qty,
                        price=intent.price,
                        status="rejected",
                        message=limit_reason,
                    )
                )
                self.db.flush()
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="rejected",
                message=limit_reason,
            )

        if intent.mode == "paper":
            return self.paper.place_order(intent)

        gate_reason = self.risk.check_live_gates(intent)
        if gate_reason:
            self.db.add(
                LiveOrder(
                    client_order_id=intent.client_order_id,
                    symbol=intent.symbol,
                    side=intent.side.value,
                    qty=intent.qty,
                    price=intent.price,
                    status="rejected",
                    message=gate_reason,
                )
            )
            self.db.flush()
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="rejected",
                message=gate_reason,
            )

        from desk_broker.trading_mode import live_execution_mode

        mode = live_execution_mode()
        if mode == "blocked":
            msg = "auto live blocked: I_UNDERSTAND_AUTO_LIVE required"
            self.db.add(
                LiveOrder(
                    client_order_id=intent.client_order_id,
                    symbol=intent.symbol,
                    side=intent.side.value,
                    qty=intent.qty,
                    price=intent.price,
                    status="rejected",
                    message=msg,
                )
            )
            self.db.flush()
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="rejected",
                message=msg,
            )
        if mode == "approval":
            self.db.add(
                LiveOrder(
                    client_order_id=intent.client_order_id,
                    symbol=intent.symbol,
                    side=intent.side.value,
                    qty=intent.qty,
                    price=intent.price,
                    status="awaiting_approval",
                    message="awaiting manual approval",
                )
            )
            self.db.flush()
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="awaiting_approval",
                message="awaiting manual approval",
            )

        result = self.live.place_order(intent)
        if result.status == "filled" and intent.price:
            self.risk.daily_used += float(intent.price) * float(intent.qty)
        return result

    def list_approvals(self) -> list[dict]:
        """待审批实盘订单。"""
        rows = self.db.scalars(
            select(LiveOrder)
            .where(LiveOrder.status == "awaiting_approval")
            .order_by(LiveOrder.id.desc())
        ).all()
        return [
            {
                "id": r.id,
                "client_order_id": r.client_order_id,
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "price": r.price,
                "status": r.status,
                "message": r.message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def approve_order(self, client_order_id: str) -> OrderResult:
        """
        审批通过后按自动实盘路径成交（仍受 auto 开关约束）。

        审批本身表示人工确认；成交仍要求 ``AUTO_EXECUTE_LIVE``+确认变量，
        否则保持 awaiting 并提示打开自动开关（或在此强制走 Mock 一次）。
        为便于运营：审批通过即允许本次 Mock/柜台成交，不二次要求 auto 开关。
        """
        row = self.db.scalar(
            select(LiveOrder).where(LiveOrder.client_order_id == client_order_id)
        )
        if not row or row.status != "awaiting_approval":
            return OrderResult(
                client_order_id=client_order_id,
                status="rejected",
                message="approval not found",
            )
        intent = OrderIntent(
            symbol=row.symbol,
            side=Side(row.side),
            qty=float(row.qty),
            price=float(row.price) if row.price is not None else None,
            client_order_id=f"{row.client_order_id}|approved",
            mode="live",
        )
        # 直接交 Mock/QmtBroker，跳过再次审批
        result = MockQmtBroker(self.db).place_order(intent)
        row.status = result.status
        row.message = f"approved: {result.message}"
        row.broker_order_id = result.broker_order_id
        self.db.flush()
        return result

    def reject_order(self, client_order_id: str) -> dict:
        """拒绝待审批订单。"""
        row = self.db.scalar(
            select(LiveOrder).where(LiveOrder.client_order_id == client_order_id)
        )
        if not row or row.status != "awaiting_approval":
            return {"ok": False, "message": "approval not found"}
        row.status = "rejected"
        row.message = "rejected by operator"
        self.db.flush()
        return {"ok": True, "client_order_id": client_order_id, "status": "rejected"}


from desk_broker.paper_runner import PaperStrategyRunner  # noqa: E402

__all__ = [
    "Broker",
    "PaperBroker",
    "RiskGate",
    "BrokerGateway",
    "PaperStrategyRunner",
]
