"""模拟盘 / 实盘网关。"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_broker import BrokerGateway
from desk_common.contracts import OrderIntent, Side
from desk_common.settings import get_settings
from desk_db import get_db

router = APIRouter(prefix="/broker")


class OrderIn(BaseModel):
    symbol: str
    side: Side
    qty: float
    price: float | None = None
    mode: str | None = None
    strategy_id: str | None = None


class RunnerSettingsIn(BaseModel):
    """Paper Runner 调度开关。"""

    enabled: bool | None = None
    strategy_id: str | None = None
    interval_minutes: int | None = None


class PaperRunIn(BaseModel):
    """单标的纸交易策略跑一次。"""

    strategy_id: str
    symbol: str


class PaperWatchRunIn(BaseModel):
    """自选批量纸交易策略跑一次。"""

    strategy_id: str


class PaperSeedIn(BaseModel):
    """模拟盘手动建仓。"""

    symbol: str
    qty: float | None = None
    price: float | None = None
    strategy_id: str | None = None
    capital_pct: float | None = None
    add_watchlist: bool = True
    name: str | None = None


class PaperPositionStrategyIn(BaseModel):
    """更换模拟持仓执行策略。"""

    strategy_id: str


class PaperSellIn(BaseModel):
    """模拟盘手动卖出。"""

    symbol: str
    qty: float | None = None
    price: float | None = None


class RiskIn(BaseModel):
    armed: bool | None = None
    kill_switch: bool | None = None
    whitelist: list[str] | None = None
    max_order_position_pct: float | None = None
    max_order_notional: float | None = None
    max_daily_notional: float | None = None


_GATE: BrokerGateway | None = None


def get_gate(db: Session) -> BrokerGateway:
    global _GATE
    if _GATE is None or _GATE.db is not db:
        _GATE = BrokerGateway(db)
    else:
        _GATE.db = db
        _GATE.paper.db = db
        _GATE.live.db = db
    return _GATE


@router.get("/paper")
def paper_summary(db: Session = Depends(get_db)):
    return get_gate(db).paper.summary()


@router.post("/paper/reset")
def paper_reset(db: Session = Depends(get_db)):
    """重置模拟账户持仓与成交流水。"""
    return get_gate(db).paper.reset_account()


@router.post("/paper/seed")
def paper_seed(body: PaperSeedIn, db: Session = Depends(get_db)):
    """
    模拟盘手动添加股票到持仓（豁免策略生命周期与单笔限额）。

    默认同时写入自选；价格优先用请求值，否则盘中快照 / 日线。
    """
    from desk_common.symbols import normalize_symbol
    from desk_market import MarketService

    sym = normalize_symbol(body.symbol)
    if body.add_watchlist:
        MarketService(db).add_watchlist(sym, body.name or sym)

    price = body.price
    if price is None or float(price) <= 0:
        try:
            from app.routes.market import get_market_data

            snap = (get_market_data().get_snapshots([sym]) or {}).get(sym) or {}
            last = snap.get("last")
            if last is not None and float(last) > 0:
                price = float(last)
        except Exception:  # noqa: BLE001
            price = None

    return get_gate(db).seed_paper_position(
        sym,
        qty=body.qty,
        price=price,
        strategy_id=body.strategy_id,
        capital_pct=body.capital_pct,
    )


@router.post("/paper/sell")
def paper_sell(body: PaperSellIn, db: Session = Depends(get_db)):
    """
    模拟盘手动卖出持仓（默认全平；可指定数量）。

    价格优先用请求值，否则盘中快照 / 日线 / 成本价。
    """
    from desk_common.symbols import normalize_symbol

    sym = normalize_symbol(body.symbol)
    price = body.price
    if price is None or float(price) <= 0:
        try:
            from app.routes.market import get_market_data

            snap = (get_market_data().get_snapshots([sym]) or {}).get(sym) or {}
            last = snap.get("last")
            if last is not None and float(last) > 0:
                price = float(last)
        except Exception:  # noqa: BLE001
            price = None

    return get_gate(db).sell_paper_position(sym, qty=body.qty, price=price)


@router.post("/paper/positions/{symbol}/strategy")
def paper_position_strategy(
    symbol: str, body: PaperPositionStrategyIn, db: Session = Depends(get_db)
):
    """更换模拟持仓的执行策略。"""
    result = get_gate(db).set_paper_position_strategy(symbol, body.strategy_id)
    if not result.get("ok"):
        raise HTTPException(404, result.get("message") or "not found")
    return result


@router.post("/live/positions/{symbol}/strategy")
def live_position_strategy(
    symbol: str, body: PaperPositionStrategyIn, db: Session = Depends(get_db)
):
    """更换实盘持仓的执行策略标签。"""
    return get_gate(db).set_live_position_strategy(symbol, body.strategy_id)


@router.post("/paper/run-once")
def paper_run_once(body: PaperRunIn, db: Session = Depends(get_db)):
    """对单标的跑一次纸交易策略评估并下单。"""
    from desk_broker.paper_runner import PaperStrategyRunner

    return PaperStrategyRunner(db).run_once(
        strategy_id=body.strategy_id, symbol=body.symbol
    )


@router.post("/paper/run-watchlist")
def paper_run_watchlist(body: PaperWatchRunIn, db: Session = Depends(get_db)):
    """对自选全部标的跑一次纸交易策略。"""
    from desk_broker.paper_runner import PaperStrategyRunner

    return PaperStrategyRunner(db).run_watchlist(strategy_id=body.strategy_id)


@router.get("/qmt/ping")
def qmt_ping(db: Session = Depends(get_db)):
    return get_gate(db).live.ping()


@router.get("/live/positions")
def live_positions(db: Session = Depends(get_db)):
    """
    实盘持仓：优先 QMT ``query_stock_positions``，否则本地 live_positions。
    """
    return get_gate(db).live.account_snapshot()


@router.get("/risk")
def risk_state(db: Session = Depends(get_db)):
    g = get_gate(db)
    # 限额以设置页为准，展示前同步
    g.risk.apply_from_settings()
    return {
        "armed": g.risk.armed,
        "kill_switch": g.risk.kill_switch,
        "whitelist": sorted(g.risk.whitelist),
        "max_order_position_pct": g.risk.max_order_position_pct,
        "max_order_notional": g.risk.max_order_notional,
        "max_daily_notional": g.risk.max_daily_notional,
        "max_positions": g.risk.max_positions,
        "daily_used": g.risk.daily_used,
    }


@router.post("/risk")
def risk_update(body: RiskIn, db: Session = Depends(get_db)):
    """
    更新 ARM/Kill/白名单并持久化到 .env（与设置页同源）。

    金额仓位限额请走设置页；本接口供监控页应急 Kill 等快捷操作。
    """
    from desk_common.settings_store import apply_settings_patch

    patch: dict = {}
    if body.armed is not None:
        patch["risk_armed"] = body.armed
    if body.kill_switch is not None:
        patch["risk_kill_switch"] = body.kill_switch
    if body.whitelist is not None:
        patch["risk_whitelist"] = ",".join(sorted({s.strip().upper() for s in body.whitelist if s.strip()}))
    # 限额若传入也写入（兼容旧客户端）
    if body.max_order_position_pct is not None:
        patch["risk_max_order_position_pct"] = body.max_order_position_pct
    if body.max_order_notional is not None:
        patch["risk_max_order_notional"] = body.max_order_notional
    if body.max_daily_notional is not None:
        patch["risk_max_daily_notional"] = body.max_daily_notional
    if patch:
        apply_settings_patch(patch)
    return risk_state(db)


@router.get("/approvals")
def list_approvals(db: Session = Depends(get_db)):
    """待审批实盘订单列表。"""
    return {"items": get_gate(db).list_approvals()}


@router.post("/approvals/{client_order_id}/approve")
def approve_order(client_order_id: str, db: Session = Depends(get_db)):
    """批准并成交待审批订单。"""
    return get_gate(db).approve_order(client_order_id).model_dump()


@router.post("/approvals/{client_order_id}/reject")
def reject_order(client_order_id: str, db: Session = Depends(get_db)):
    """拒绝待审批订单。"""
    return get_gate(db).reject_order(client_order_id)


@router.get("/trading-mode")
def trading_mode_state():
    """纸/审批/自动模式状态。"""
    from desk_broker.trading_mode import live_execution_mode

    settings = get_settings()
    return {
        "trade_mode": settings.trade_mode,
        "auto_execute_live": settings.auto_execute_live,
        "i_understand_auto_live": settings.i_understand_auto_live,
        "live_execution": live_execution_mode(settings),
    }


@router.get("/paper/runner")
def paper_runner_status():
    """Paper Runner 定时状态。"""
    from desk_broker.runner_scheduler import get_runner_status

    return get_runner_status()


@router.post("/paper/runner")
def paper_runner_update(body: RunnerSettingsIn):
    """
    更新 Runner 调度配置（写 .env）。

    注意：间隔/开关变更后需重启 API 进程才会重注册 APScheduler job。
    """
    from desk_common.settings_store import apply_settings_patch

    patch: dict = {}
    if body.enabled is not None:
        patch["paper_runner_enabled"] = body.enabled
    if body.strategy_id is not None:
        patch["paper_runner_strategy_id"] = body.strategy_id
    if body.interval_minutes is not None:
        patch["paper_runner_interval_minutes"] = body.interval_minutes
    if patch:
        apply_settings_patch(patch)
    from desk_broker.runner_scheduler import get_runner_status

    return {
        **get_runner_status(),
        "note": "启用/改间隔后请重启 API 以使调度器重载",
    }


@router.post("/order")
def place_order(body: OrderIn, db: Session = Depends(get_db)):
    settings = get_settings()
    mode = body.mode or settings.trade_mode
    intent = OrderIntent(
        symbol=body.symbol,
        side=body.side,
        qty=body.qty,
        price=body.price,
        client_order_id=uuid4().hex,
        strategy_id=body.strategy_id or settings.paper_default_strategy_id,
        mode=mode,  # type: ignore[arg-type]
    )
    return get_gate(db).place_order(intent).model_dump()
