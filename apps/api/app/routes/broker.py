"""模拟盘 / 实盘网关。"""

from uuid import uuid4

from fastapi import APIRouter, Depends
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


class PaperRunIn(BaseModel):
    """单标的纸交易策略跑一次。"""

    strategy_id: str
    symbol: str


class PaperWatchRunIn(BaseModel):
    """自选批量纸交易策略跑一次。"""

    strategy_id: str


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
        "daily_used": g.risk.daily_used,
    }


@router.post("/risk")
def risk_update(body: RiskIn, db: Session = Depends(get_db)):
    """更新 ARM/Kill/白名单；金额仓位限额请走设置页（写入 .env）。"""
    g = get_gate(db)
    if body.armed is not None:
        g.risk.armed = body.armed
    if body.kill_switch is not None:
        g.risk.kill_switch = body.kill_switch
    if body.whitelist is not None:
        g.risk.whitelist = set(body.whitelist)
    # 限额字段若传入则忽略内存覆盖，始终以 Settings 为准
    g.risk.apply_from_settings()
    return risk_state(db)


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
        mode=mode,  # type: ignore[arg-type]
    )
    return get_gate(db).place_order(intent).model_dump()
