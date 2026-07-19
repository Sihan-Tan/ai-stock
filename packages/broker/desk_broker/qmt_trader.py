"""miniQMT XtQuantTrader 薄封装（真单下单）。"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_TRADER: Any = None
_ACCOUNT: Any = None
_CONNECTED = False


def qmt_available() -> bool:
    """是否可 import xtquant.xttrader。"""
    try:
        import xtquant.xttrader  # type: ignore  # noqa: F401
        import xtquant.xtconstant  # type: ignore  # noqa: F401
        from xtquant.xttype import StockAccount  # type: ignore  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def connect_qmt(*, userdata_path: str, account_id: str) -> dict[str, Any]:
    """
    连接 miniQMT 交易端（单例）。

    @param userdata_path: QMT userdata_mini 路径
    @param account_id: 资金账号
    """
    global _TRADER, _ACCOUNT, _CONNECTED
    if _CONNECTED and _TRADER is not None and _ACCOUNT is not None:
        return {"connected": True, "mode": "qmt", "account_id": account_id}

    from xtquant.xttrader import XtQuantTrader  # type: ignore
    from xtquant.xttype import StockAccount  # type: ignore

    if not userdata_path or not account_id:
        raise RuntimeError("QMT_USERDATA_PATH and QMT_ACCOUNT_ID required for real orders")

    session_id = int(time.time()) * 1000 + (os.getpid() % 1000)
    trader = XtQuantTrader(userdata_path, session_id)
    account = StockAccount(account_id)
    trader.start()
    # connect 同步；失败则抛错
    result = trader.connect()
    if result != 0:
        try:
            trader.stop()
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"XtQuantTrader.connect failed: {result}")
    sub = trader.subscribe(account)
    if sub != 0:
        logger.warning("subscribe account returned %s", sub)

    _TRADER = trader
    _ACCOUNT = account
    _CONNECTED = True
    return {"connected": True, "mode": "qmt", "account_id": account_id, "session_id": session_id}


def place_stock_order(
    *,
    symbol: str,
    side: str,
    qty: float,
    price: float | None,
    strategy_name: str = "desk",
    remark: str = "",
) -> dict[str, Any]:
    """
    限价/市价委托。

    @param symbol: 如 600519.SH
    @param side: buy/sell
    @param qty: 股数
    @param price: >0 限价；否则市价保护
    @returns: order_id / status / message
    """
    from xtquant import xtconstant  # type: ignore

    if not _CONNECTED or _TRADER is None or _ACCOUNT is None:
        raise RuntimeError("QMT not connected")

    volume = int(qty)
    if volume < 100:
        raise RuntimeError("qty must be >= 100")

    code = symbol.strip().upper()
    if price and float(price) > 0:
        price_type = xtconstant.FIX_PRICE
        px = float(price)
    else:
        price_type = (
            xtconstant.MARKET_SH_CONVERT_5_LIMIT
            if code.endswith(".SH")
            else xtconstant.MARKET_SZ_CONVERT_5_CANCEL
        )
        px = 0.0

    order_type = xtconstant.STOCK_BUY if side == "buy" else xtconstant.STOCK_SELL
    order_id = _TRADER.order_stock(
        _ACCOUNT,
        code,
        order_type,
        volume,
        price_type,
        px,
        strategy_name or "desk",
        remark or "",
    )
    if order_id is None or order_id < 0:
        return {
            "ok": False,
            "order_id": order_id,
            "message": f"order_stock failed: {order_id}",
        }
    return {
        "ok": True,
        "order_id": order_id,
        "message": "qmt order submitted",
        "price_type": "limit" if px > 0 else "market",
    }


def disconnect_qmt() -> None:
    """断开交易连接。"""
    global _TRADER, _ACCOUNT, _CONNECTED
    if _TRADER is not None:
        try:
            _TRADER.stop()
        except Exception:  # noqa: BLE001
            logger.exception("qmt stop failed")
    _TRADER = None
    _ACCOUNT = None
    _CONNECTED = False
