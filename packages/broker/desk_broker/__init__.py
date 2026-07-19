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

# 监控页「添加股票」等手动建仓：不走策略生命周期闸门
MANUAL_PAPER_STRATEGY_ID = "manual"


def _strategy_from_client_order_id(client_order_id: str) -> str | None:
    """
    从 client_order_id 解析策略 ID。

    新格式 ``seed|{strategy_id}|{symbol}|…`` / ``paper|{strategy_id}|{symbol}|…``；
    旧格式 ``seed|{symbol}|…`` 视为 manual。
    """
    parts = (client_order_id or "").split("|")
    if not parts:
        return None
    if parts[0] == "seed":
        if len(parts) >= 4:
            return parts[1] or MANUAL_PAPER_STRATEGY_ID
        return MANUAL_PAPER_STRATEGY_ID
    if parts[0] == "paper" and len(parts) >= 3:
        return parts[1] or None
    return None


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
        # 持仓 strategy_id 优先；旧数据回退从最近订单解析
        orders = self.db.scalars(
            select(PaperOrder)
            .where(PaperOrder.account_id == acc.id)
            .order_by(PaperOrder.id.desc())
        ).all()
        strategy_by_symbol: dict[str, str] = {}
        for order in orders:
            if order.symbol in strategy_by_symbol:
                continue
            sid = _strategy_from_client_order_id(order.client_order_id)
            if sid:
                strategy_by_symbol[order.symbol] = sid
        settings = get_settings()
        self.db.flush()
        return {
            "cash": acc.cash,
            "equity": acc.equity,
            "initial_cash": settings.paper_initial_cash,
            "account": acc.name,
            "updated_at": acc.updated_at.isoformat() if acc.updated_at else None,
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "cost": p.cost,
                    "strategy_id": getattr(p, "strategy_id", None)
                    or strategy_by_symbol.get(p.symbol),
                }
                for p in positions
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
            sid = (intent.strategy_id or "").strip() or None
            if not pos:
                self.db.add(
                    PaperPosition(
                        account_id=acc.id,
                        symbol=intent.symbol,
                        qty=intent.qty,
                        cost=price,
                        strategy_id=sid,
                    )
                )
            else:
                new_qty = pos.qty + intent.qty
                pos.cost = (pos.cost * pos.qty + price * intent.qty) / new_qty
                pos.qty = new_qty
                if sid:
                    pos.strategy_id = sid
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
    max_positions: int = 4
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

    def check_max_positions(
        self, intent: OrderIntent, *, held_symbols: set[str]
    ) -> str | None:
        """
        最多持仓股票只数（买入新标的时校验；加仓已有标的不计入新增）。

        @param held_symbols: 当前持仓代码集合（qty>0）
        @returns: 拒绝原因；通过则 None。max_positions<=0 表示不限制
        """
        if intent.side != Side.BUY:
            return None
        max_n = int(self.max_positions)
        if max_n <= 0:
            return None
        sym = (intent.symbol or "").strip().upper()
        if not sym:
            return None
        if sym in held_symbols:
            return None
        if len(held_symbols) >= max_n:
            return f"exceeds max positions ({max_n})"
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
        """从 Settings（.env / 设置页）同步限额与实盘闸门，作为唯一来源。"""
        settings = get_settings()
        self.max_order_position_pct = float(settings.risk_max_order_position_pct)
        self.max_order_notional = float(settings.risk_max_order_notional)
        self.max_daily_notional = float(settings.risk_max_daily_notional)
        self.max_positions = int(settings.risk_max_positions)
        self.armed = bool(settings.risk_armed)
        self.kill_switch = bool(settings.risk_kill_switch)
        raw = (settings.risk_whitelist or "").replace("，", ",")
        self.whitelist = {
            p.strip().upper() for p in raw.split(",") if p.strip()
        }


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

    def _live_rows_from_db(self) -> tuple[list[dict], list[dict]]:
        """
        从本地 live_positions 拆出持仓 / 已卖出。

        @returns: (holding_rows, sold_rows)
        """
        rows = self.db.scalars(select(LivePosition)).all()
        holdings: list[dict] = []
        sold: list[dict] = []
        for p in rows:
            item = {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "can_use_qty": float(p.qty) if float(p.qty) > 0 else 0.0,
                "cost": float(p.cost),
                "market_value": float(p.qty) * float(p.cost),
                "frozen_qty": 0.0,
                "yesterday_qty": None,
                "strategy_id": getattr(p, "strategy_id", None) or "manual",
                "row_type": "holding" if float(p.qty) > 0 else "sold",
            }
            if float(p.qty) > 0:
                holdings.append(item)
            else:
                sold.append(item)
        return holdings, sold

    def _sync_live_positions(self, qmt_positions: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        用柜台持仓回写 live_positions，并标出已清仓标的。

        @param qmt_positions: query_stock_positions 结果
        @returns: (holding_rows, sold_rows)
        """
        existing = {
            p.symbol: p
            for p in self.db.scalars(select(LivePosition)).all()
        }
        held_syms: set[str] = set()
        holdings: list[dict] = []
        now = datetime.utcnow()
        for raw in qmt_positions:
            sym = str(raw.get("symbol") or "").strip().upper()
            if not sym:
                continue
            held_syms.add(sym)
            qty = float(raw.get("qty") or 0)
            cost = float(raw.get("cost") or 0)
            row = existing.get(sym)
            if row:
                row.qty = qty
                if cost > 0:
                    row.cost = cost
                row.updated_at = now
            else:
                row = LivePosition(
                    symbol=sym,
                    qty=qty,
                    cost=cost if cost > 0 else 0.0,
                    strategy_id="manual",
                    updated_at=now,
                )
                self.db.add(row)
                existing[sym] = row
            sid = getattr(row, "strategy_id", None) or "manual"
            holdings.append(
                {
                    **raw,
                    "symbol": sym,
                    "strategy_id": sid,
                    "row_type": "holding",
                }
            )
        sold: list[dict] = []
        for sym, row in existing.items():
            if sym in held_syms:
                continue
            prev_qty = float(row.qty or 0)
            if prev_qty > 0:
                row.qty = 0.0
                row.updated_at = now
            sold.append(
                {
                    "symbol": sym,
                    "qty": prev_qty if prev_qty > 0 else 0.0,
                    "can_use_qty": 0.0,
                    "cost": float(row.cost or 0),
                    "market_value": 0.0,
                    "frozen_qty": 0.0,
                    "yesterday_qty": None,
                    "strategy_id": getattr(row, "strategy_id", None) or "manual",
                    "row_type": "sold",
                }
            )
        self.db.flush()
        return holdings, sold

    def account_snapshot(self) -> dict:
        """
        实盘持仓快照（Mock：读本地 live_positions）。

        @returns: source / mode / asset / positions / sold / message
        """
        holdings, sold = self._live_rows_from_db()
        mv = sum(float(p["market_value"]) for p in holdings)
        return {
            "source": "local_db",
            "mode": self.mode,
            "asset": {
                "cash": None,
                "frozen_cash": None,
                "market_value": mv,
                "total_asset": mv,
                "account_id": get_settings().qmt_account_id or "mock",
            },
            "positions": holdings,
            "sold": sold,
            "message": "当前为 Mock/本地库持仓；配置 QMT 真连后可看柜台持仓",
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
    miniQMT 适配：探测 xtquant；``QMT_FORCE_MOCK=0`` 且账号齐全时发真单。
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self._xt = None
        try:
            from desk_broker.qmt_trader import qmt_available

            if qmt_available():
                self._xt = True
                self.mode = "qmt"
                self.connected = True
            else:
                self._xt = None
                self.mode = "mock"
                self.connected = True
        except Exception:  # noqa: BLE001
            self._xt = None
            self.mode = "mock"
            self.connected = True

    def ping(self) -> dict:
        """连通探测（含 force_mock / 账号配置）。"""
        settings = get_settings()
        query_ready = self._qmt_query_ready()
        real_ready = query_ready and not bool(settings.qmt_force_mock)
        base = super().ping()
        base.update(
            {
                "xtquant": bool(self._xt),
                "force_mock": bool(settings.qmt_force_mock),
                "account_configured": bool(settings.qmt_account_id),
                "query_ready": query_ready,
                "real_ready": real_ready,
            }
        )
        return base

    def _qmt_query_ready(self) -> bool:
        """
        是否可连接柜台读持仓/资产。

        仅需 xtquant + 路径 + 账号；``QMT_FORCE_MOCK`` 只拦真下单，不拦查询。
        """
        settings = get_settings()
        return bool(
            self._xt and settings.qmt_account_id and settings.qmt_userdata_path
        )

    def _real_qmt_ready(self) -> bool:
        """是否具备向柜台发真单的配置（需关闭 force_mock）。"""
        return self._qmt_query_ready() and not bool(get_settings().qmt_force_mock)

    def account_snapshot(self) -> dict:
        """
        优先查 QMT 柜台持仓与资产；不可用时回退本地 live_positions。

        读持仓不依赖 ``QMT_FORCE_MOCK``（该开关仅控制是否发真单）。
        """
        if not self._qmt_query_ready():
            snap = super().account_snapshot()
            snap["message"] = (
                "未配置 QMT 路径/账号或 xtquant 不可用，展示本地 live_positions"
            )
            return snap
        settings = get_settings()
        try:
            from desk_broker.qmt_trader import (
                connect_qmt,
                query_stock_asset,
                query_stock_positions,
            )

            connect_qmt(
                userdata_path=settings.qmt_userdata_path,
                account_id=settings.qmt_account_id,
            )
            qmt_positions = query_stock_positions()
            asset = query_stock_asset()
            holdings, sold = self._sync_live_positions(qmt_positions)
            note = ""
            if settings.qmt_force_mock:
                note = "持仓来自 QMT 柜台；当前 QMT_FORCE_MOCK=1，下单仍走 Mock"
            return {
                "source": "qmt",
                "mode": "qmt",
                "asset": asset,
                "positions": holdings,
                "sold": sold,
                "message": note,
            }
        except Exception as exc:  # noqa: BLE001
            base = super().account_snapshot()
            base["message"] = f"QMT 持仓查询失败，已回退本地库：{exc}"
            return base

    def place_order(self, intent: OrderIntent) -> OrderResult:
        """
        自动实盘成交：需双开关；真单另需 ``QMT_FORCE_MOCK=0`` + 账号。
        """
        from desk_broker.trading_mode import auto_live_allowed

        if not auto_live_allowed():
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="rejected",
                message="auto live blocked: set AUTO_EXECUTE_LIVE=1 and I_UNDERSTAND_AUTO_LIVE=1",
            )
        return self.submit(intent)

    def submit(self, intent: OrderIntent) -> OrderResult:
        """
        提交实盘单（审批通过后可直接调用，不再校验自动开关）。

        真单条件：xtquant 可用、未 force_mock、路径与账号已配置；否则 Mock 落库。
        """
        settings = get_settings()
        use_real = bool(
            self._xt
            and not settings.qmt_force_mock
            and settings.qmt_account_id
            and settings.qmt_userdata_path
        )
        if use_real:
            try:
                from desk_broker.qmt_trader import connect_qmt, place_stock_order

                connect_qmt(
                    userdata_path=settings.qmt_userdata_path,
                    account_id=settings.qmt_account_id,
                )
                placed = place_stock_order(
                    symbol=intent.symbol,
                    side=intent.side.value,
                    qty=float(intent.qty),
                    price=float(intent.price) if intent.price else None,
                    strategy_name=intent.strategy_id or "desk",
                    remark=intent.client_order_id[:24],
                )
                if not placed.get("ok"):
                    self.db.add(
                        LiveOrder(
                            client_order_id=intent.client_order_id,
                            symbol=intent.symbol,
                            side=intent.side.value,
                            qty=intent.qty,
                            price=intent.price,
                            status="rejected",
                            message=str(placed.get("message") or "qmt reject"),
                        )
                    )
                    self.db.flush()
                    return OrderResult(
                        client_order_id=intent.client_order_id,
                        status="rejected",
                        message=str(placed.get("message") or "qmt reject"),
                    )
                oid = str(placed.get("order_id"))
                self.db.add(
                    LiveOrder(
                        client_order_id=intent.client_order_id,
                        broker_order_id=oid,
                        symbol=intent.symbol,
                        side=intent.side.value,
                        qty=intent.qty,
                        price=intent.price,
                        status="accepted",
                        message="qmt order submitted (await exchange fill)",
                    )
                )
                self.db.flush()
                return OrderResult(
                    client_order_id=intent.client_order_id,
                    status="accepted",
                    filled_qty=0.0,
                    avg_price=intent.price,
                    broker_order_id=oid,
                    message="qmt order submitted",
                )
            except Exception as exc:  # noqa: BLE001
                self.db.add(
                    LiveOrder(
                        client_order_id=intent.client_order_id,
                        symbol=intent.symbol,
                        side=intent.side.value,
                        qty=intent.qty,
                        price=intent.price,
                        status="rejected",
                        message=f"qmt error: {exc}",
                    )
                )
                self.db.flush()
                return OrderResult(
                    client_order_id=intent.client_order_id,
                    status="rejected",
                    message=f"qmt error: {exc}",
                )

        result = super().place_order(intent)
        tag = "force_mock" if settings.qmt_force_mock else "no xtquant/account"
        result.message = f"{result.message or 'mock'}; ({tag})"
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

    def _held_symbols(self, mode: str) -> set[str]:
        """
        当前持仓标的集合（qty>0）。

        @param mode: paper / live
        """
        if mode == "paper":
            acc = self.paper._ensure_account()
            rows = self.db.scalars(
                select(PaperPosition).where(PaperPosition.account_id == acc.id)
            ).all()
            return {p.symbol.strip().upper() for p in rows if float(p.qty) > 0}
        rows = self.db.scalars(select(LivePosition)).all()
        return {p.symbol.strip().upper() for p in rows if float(p.qty) > 0}

    def place_order(self, intent: OrderIntent) -> OrderResult:
        """
        按 mode 路由。

        设置页「下单限额」每次下单前从 Settings 同步，对 **模拟与实盘** 均强制生效；
        「最多持仓只数」对含手动建仓在内的买入新标的生效；
        ``strategy_id=manual`` 的纸买豁免金额限额与生命周期闸门；
        实盘额外要求 Kill/ARM/白名单。
        """
        # 限额以设置/.env 为准，避免被风控页内存值覆盖后长期偏离
        self.risk.apply_from_settings()
        is_seed_paper = intent.mode == "paper" and (intent.client_order_id or "").startswith(
            "seed|"
        )
        is_manual_paper = intent.mode == "paper" and (
            (intent.strategy_id or "").strip() == MANUAL_PAPER_STRATEGY_ID or is_seed_paper
        )
        pos_reason = self.risk.check_max_positions(
            intent, held_symbols=self._held_symbols(intent.mode)
        )
        if pos_reason:
            if intent.mode != "paper":
                self.db.add(
                    LiveOrder(
                        client_order_id=intent.client_order_id,
                        symbol=intent.symbol,
                        side=intent.side.value,
                        qty=intent.qty,
                        price=intent.price,
                        status="rejected",
                        message=pos_reason,
                    )
                )
                self.db.flush()
            return OrderResult(
                client_order_id=intent.client_order_id,
                status="rejected",
                message=pos_reason,
            )

        if not is_manual_paper:
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
            if not is_manual_paper:
                paper_gate = self._check_paper_lifecycle_buy(intent)
                if paper_gate:
                    return OrderResult(
                        client_order_id=intent.client_order_id,
                        status="rejected",
                        message=paper_gate,
                    )
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
        if result.status in ("filled", "accepted") and intent.price:
            self.risk.daily_used += float(intent.price) * float(intent.qty)
        return result

    def seed_paper_position(
        self,
        symbol: str,
        *,
        qty: float | None = None,
        price: float | None = None,
        strategy_id: str | None = None,
        capital_pct: float | None = None,
    ) -> dict:
        """
        监控页「添加股票」：规范化代码、解析价格并纸买建仓。

        ``client_order_id`` 以 ``seed|`` 开头，豁免生命周期与单笔限额；仍受现金与最多持仓数约束。
        未指定数量时默认 100 股；可按 ``capital_pct``（占可用现金比例，0–1 或 1–100）估算股数。

        @param symbol: 原始代码
        @param qty: 股数；None 则自动或由仓位推算
        @param price: 成交价；None 则取快照/日线，再不行用 10
        @param strategy_id: 关联策略；默认 manual
        @param capital_pct: 仓位比例（优先于 qty）
        @returns: 含 order 结果与规范化 symbol 的字典
        """
        from desk_common.symbols import normalize_symbol

        sym = normalize_symbol(symbol)
        sid = (strategy_id or MANUAL_PAPER_STRATEGY_ID).strip() or MANUAL_PAPER_STRATEGY_ID
        px = price if price is not None and float(price) > 0 else None
        if px is None:
            px = self.paper._last_price(sym, fallback=10.0) or 10.0
        px = float(px)
        if px <= 0:
            return {
                "status": "rejected",
                "symbol": sym,
                "message": "无法解析价格，请手动指定 price",
            }

        acc = self.paper._ensure_account()
        cash = float(acc.cash)
        # 预留约 0.3% 费用缓冲
        affordable = int(cash / (px * 1.003) / 100) * 100
        want: float
        if capital_pct is not None and float(capital_pct) > 0:
            raw = float(capital_pct)
            pct = raw / 100.0 if raw > 1.0 else raw
            pct = min(max(pct, 0.01), 1.0)
            want = float(int(cash * pct / (px * 1.003) / 100) * 100)
        elif qty is not None and float(qty) > 0:
            want = float(int(float(qty) / 100) * 100)
        else:
            want = 100.0
        if want < 100:
            want = 100.0
        final_qty = min(want, float(affordable))
        if final_qty < 100:
            return {
                "status": "rejected",
                "symbol": sym,
                "price": px,
                "message": f"现金不足：现价约 {px:.2f}，至少需约 {px * 100 * 1.003:.0f} 元买 1 手",
            }

        result = self.place_order(
            OrderIntent(
                symbol=sym,
                side=Side.BUY,
                qty=final_qty,
                price=px,
                client_order_id=f"seed|{sid}|{sym}|{uuid4().hex[:10]}",
                strategy_id=sid,
                mode="paper",
            )
        )
        return {
            "status": result.status,
            "symbol": sym,
            "qty": final_qty,
            "price": px,
            "strategy_id": sid,
            "client_order_id": result.client_order_id,
            "filled_qty": result.filled_qty,
            "avg_price": result.avg_price,
            "message": result.message,
        }

    def set_paper_position_strategy(self, symbol: str, strategy_id: str) -> dict:
        """
        更换模拟持仓的执行策略（不改持仓数量/成本）。

        @param symbol: 标的
        @param strategy_id: 新策略 ID（含 manual）
        @returns: {ok, symbol, strategy_id} 或失败信息
        """
        from desk_common.symbols import normalize_symbol

        sym = normalize_symbol(symbol)
        sid = (strategy_id or MANUAL_PAPER_STRATEGY_ID).strip() or MANUAL_PAPER_STRATEGY_ID
        acc = self.paper._ensure_account()
        pos = self.db.scalar(
            select(PaperPosition).where(
                PaperPosition.account_id == acc.id, PaperPosition.symbol == sym
            )
        )
        if not pos:
            return {"ok": False, "symbol": sym, "message": "持仓不存在"}
        pos.strategy_id = sid
        self.db.flush()
        return {"ok": True, "symbol": sym, "strategy_id": sid}

    def set_live_position_strategy(self, symbol: str, strategy_id: str) -> dict:
        """
        更换实盘持仓的执行策略标签（不改柜台数量）。

        @param symbol: 标的
        @param strategy_id: 新策略 ID（含 manual）
        """
        from desk_common.symbols import normalize_symbol

        sym = normalize_symbol(symbol)
        sid = (strategy_id or MANUAL_PAPER_STRATEGY_ID).strip() or MANUAL_PAPER_STRATEGY_ID
        pos = self.db.scalar(select(LivePosition).where(LivePosition.symbol == sym))
        if not pos:
            pos = LivePosition(symbol=sym, qty=0.0, cost=0.0, strategy_id=sid)
            self.db.add(pos)
        else:
            pos.strategy_id = sid
        self.db.flush()
        return {"ok": True, "symbol": sym, "strategy_id": sid}

    def _check_paper_lifecycle_buy(self, intent: OrderIntent) -> str | None:
        """
        策略纸买须通过生命周期闸门（试用/主力）。

        ``strategy_id=manual``（监控页添加股票）豁免；未传时用
        ``PAPER_DEFAULT_STRATEGY_ID``，仍受闸门约束。
        """
        if intent.side != Side.BUY:
            return None
        from desk_broker.promotion_gate import buy_block_reason
        from desk_db.models import StrategyRow

        settings = get_settings()
        sid = (intent.strategy_id or settings.paper_default_strategy_id or "").strip()
        if not sid:
            return "lifecycle gate: strategy_id required for paper buy"
        if sid == MANUAL_PAPER_STRATEGY_ID:
            return None
        row = self.db.scalar(
            select(StrategyRow)
            .where(StrategyRow.strategy_id == sid)
            .order_by(StrategyRow.id.desc())
        )
        stage = str(getattr(row, "lifecycle_stage", None) or "incubating")
        reason = buy_block_reason(stage)
        if reason:
            return f"{reason}; strategy={sid}"
        return None

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
        # 人工审批后提交（可走真 QMT；跳过自动开关）
        result = self.live.submit(intent)
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
    "MANUAL_PAPER_STRATEGY_ID",
]
