"""backtrader 回测适配层。"""

from __future__ import annotations

from typing import Any

import backtrader as bt
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from desk_common.contracts import BacktestReport, BacktestRequest
from desk_common.settings import get_settings
from desk_db.models import BacktestRun
from desk_indicators import compute
from desk_market import MarketService
from desk_strategy import StrategyRegistry
from desk_backtest.commission import (
    AShareCommission,
    calc_buy_commission,
    calc_sell_fees,
)


class _PandasData(bt.feeds.PandasData):
    """标准 OHLCV feed。"""

    params = (
        ("datetime", None),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", -1),
    )


class _ASharePercentSizer(bt.Sizer):
    """按可用资金比例下单，数量向下取整到 100 股。"""

    params = (("percents", 95.0),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        if not isbuy:
            return self.broker.getposition(data).size
        price = float(data.close[0])
        if price <= 0:
            return 0
        raw = int((cash * (self.p.percents / 100.0)) / price)
        return max((raw // 100) * 100, 0)


def _bar_dt_str(strategy: bt.Strategy) -> str:
    """当前 bar 时间字符串（与 feed 对齐，避免 UTC 偏移错日）。"""
    dt = strategy.data.datetime.datetime(0)
    if hasattr(dt, "strftime"):
        # 日线 00:00:00 只保留日期，便于图表与明细阅读
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            return dt.strftime("%Y-%m-%d")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


class _SignalStrategy(bt.Strategy):
    """将 Desk 策略 on_bar 适配到 backtrader。"""

    params = (("desk_on_bar", None), ("symbol", ""), ("history_df", None), ("db", None))

    def __init__(self):
        self._order = None
        self._entry: dict[str, Any] | None = None
        self.equity_curve: list[dict[str, Any]] = []
        self.trade_list: list[dict[str, Any]] = []

    def next(self):
        self.equity_curve.append(
            {
                "date": _bar_dt_str(self),
                "value": float(self.broker.getvalue()),
            }
        )
        if self._order or not self.p.desk_on_bar:
            return

        from desk_strategy.bar_context import build_bar_row

        idx = len(self.data) - 1
        lookback = min(250, idx + 1)
        closes = [float(self.data.close[-i]) for i in range(lookback)]
        highs = [float(self.data.high[-i]) for i in range(lookback)]
        lows = [float(self.data.low[-i]) for i in range(lookback)]
        opens = [float(self.data.open[-i]) for i in range(lookback)]
        volumes = [float(self.data.volume[-i]) for i in range(lookback)]
        closes.reverse()
        highs.reverse()
        lows.reverse()
        opens.reverse()
        volumes.reverse()
        row = build_bar_row(
            self.p.symbol,
            closes=closes,
            highs=highs,
            lows=lows,
            opens=opens,
            volumes=volumes,
        )

        history = None
        hist_df = self.p.history_df
        if hist_df is not None and not getattr(hist_df, "empty", True):
            history = hist_df.iloc[: idx + 1].copy()

        signals = self.p.desk_on_bar(
            {"row": row, "history": history, "db": self.p.db}
        ) or []
        for sig in signals:
            if sig.side.value == "buy" and not self.position:
                self._order = self.buy()
                break
            if sig.side.value == "sell" and self.position:
                self._order = self.close()
                break

    def notify_order(self, order):
        """
        用成交回报拼装明细。

        backtrader 平仓后 ``trade.size=0`` 且 ``trade.price`` 只有开仓均价，
        不能直接当明细用，故在此记录开/平仓价与数量。
        """
        if order.status in (order.Canceled, order.Margin, order.Rejected):
            self._order = None
            return
        if order.status != order.Completed:
            return

        dt_str = _bar_dt_str(self)
        qty = abs(float(order.executed.size))
        price = float(order.executed.price)
        fee = get_settings()

        if order.isbuy():
            entry_comm = calc_buy_commission(
                qty * price,
                buy_commission=fee.backtest_buy_commission,
                min_commission=fee.backtest_min_commission,
            )
            # 策略仅做多；加仓时合并均价
            if self._entry is None:
                self._entry = {
                    "qty": qty,
                    "entry_price": price,
                    "dt_open": dt_str,
                    "entry_comm": entry_comm,
                }
            else:
                old_q = float(self._entry["qty"])
                old_p = float(self._entry["entry_price"])
                new_q = old_q + qty
                self._entry["entry_price"] = (
                    (old_p * old_q + price * qty) / new_q if new_q else price
                )
                self._entry["qty"] = new_q
                self._entry["entry_comm"] = float(self._entry["entry_comm"]) + entry_comm
        elif order.issell() and self._entry is not None:
            entry = self._entry
            q = min(float(entry["qty"]), qty)
            entry_price = float(entry["entry_price"])
            exit_price = price
            pnl = (exit_price - entry_price) * q
            entry_comm = float(entry["entry_comm"])
            entry_qty = float(entry["qty"]) or q
            alloc_entry_comm = entry_comm * (q / entry_qty)
            exit_comm, stamp = calc_sell_fees(
                q * exit_price,
                sell_commission=fee.backtest_sell_commission,
                stamp_duty=fee.backtest_stamp_duty,
                min_commission=fee.backtest_min_commission,
            )
            fee_total = alloc_entry_comm + exit_comm + stamp
            pnlcomm = pnl - fee_total
            notional = entry_price * q
            # 价差收益率（不含费用）；扣费收益率与账户盈亏口径一致
            ret_gross = (exit_price / entry_price - 1.0) if entry_price else 0.0
            ret_net = (pnlcomm / notional) if notional else 0.0
            self.trade_list.append(
                {
                    "side": "long",
                    "status": "closed",
                    "qty": q,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "dt_open": entry["dt_open"],
                    "dt_close": dt_str,
                    "pnl": pnl,
                    "pnlcomm": pnlcomm,
                    # 主展示用扣费后收益，避免「价差盈利但总收益亏损」误解
                    "return_pct": ret_net,
                    "return_pct_gross": ret_gross,
                    "entry_commission": alloc_entry_comm,
                    "exit_commission": exit_comm,
                    "stamp_duty": stamp,
                    "fee_total": fee_total,
                    # 兼容旧字段：总费用
                    "commission": fee_total,
                }
            )
            remain = entry_qty - q
            if remain > 1e-9:
                self._entry = {
                    "qty": remain,
                    "entry_price": entry_price,
                    "dt_open": entry["dt_open"],
                    "entry_comm": entry_comm - alloc_entry_comm,
                }
            else:
                self._entry = None

        self._order = None

    def stop(self):
        """
        回测结束时把未平仓写入明细。

        总收益按账户权益（含持仓市值），若只展示已平仓会造成「成交盈利、总收益亏损」的误解。
        """
        if self._entry is None:
            return
        entry = self._entry
        q = float(entry["qty"])
        if q <= 1e-9:
            return
        entry_price = float(entry["entry_price"])
        mark = float(self.data.close[0])
        entry_comm = float(entry["entry_comm"])
        pnl = (mark - entry_price) * q
        pnlcomm = pnl - entry_comm
        notional = entry_price * q
        ret_gross = (mark / entry_price - 1.0) if entry_price else 0.0
        ret_net = (pnlcomm / notional) if notional else 0.0
        self.trade_list.append(
            {
                "side": "long",
                "status": "open",
                "qty": q,
                "entry_price": entry_price,
                "exit_price": mark,
                "dt_open": entry["dt_open"],
                "dt_close": None,
                "pnl": pnl,
                "pnlcomm": pnlcomm,
                "return_pct": ret_net,
                "return_pct_gross": ret_gross,
                "entry_commission": entry_comm,
                "exit_commission": 0.0,
                "stamp_duty": 0.0,
                "fee_total": entry_comm,
                "commission": entry_comm,
                "mark_price": mark,
            }
        )


def _max_drawdown_from_equity(values: list[float]) -> float:
    """
    由权益序列计算最大回撤（负小数，如 -0.12）。

    @param values: 权益点
    @returns: 最大回撤
    """
    if len(values) < 2:
        return 0.0
    arr = np.asarray(values, dtype=float)
    peak = np.maximum.accumulate(arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, arr / peak - 1.0, 0.0)
    return float(np.min(dd)) if len(dd) else 0.0


def _sharpe_from_equity(values: list[float], *, periods_per_year: float = 252.0) -> float | None:
    """
    由权益序列估算年化夏普（无风险利率=0）。

    @param values: 权益点
    @param periods_per_year: 年化因子（日线 252；5 分钟约 252*48）
    """
    if len(values) < 3:
        return None
    arr = np.asarray(values, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) < 2:
        return None
    std = float(np.std(rets, ddof=1))
    if std <= 1e-12:
        return None
    return float(np.mean(rets) / std * np.sqrt(periods_per_year))


def _downsample_curve(curve: list[dict[str, Any]], max_points: int = 1500) -> list[dict[str, Any]]:
    """过长权益曲线均匀抽样，首尾保留（供前端图表）。"""
    n = len(curve)
    if n <= max_points:
        return curve
    idx = np.linspace(0, n - 1, max_points, dtype=int)
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for i in idx:
        ii = int(i)
        if ii in seen:
            continue
        seen.add(ii)
        out.append(curve[ii])
    return out


class BacktraderRunner:
    """回测运行器。"""

    def __init__(self, db: Session):
        self.db = db
        self.market = MarketService(db)
        self.registry = StrategyRegistry(db)

    def _resolve_bar_period(self, req: BacktestRequest, reg: Any) -> str:
        """请求优先，其次策略 params.bar_period，默认 1d。"""
        if req.bar_period:
            return req.bar_period
        params = getattr(reg.meta, "params", None) or {}
        period = str(params.get("bar_period") or "1d")
        return period if period in ("1d", "1m", "5m") else "1d"

    def _load_bars(self, req: BacktestRequest, period: str) -> pd.DataFrame:
        """按周期加载 OHLCV。"""
        if period == "1d":
            return self.market.load_daily_df(
                req.symbol, req.start, req.end, adj=getattr(req, "adj", "qfq")
            )
        if period == "5m":
            return self.market.load_minute_df(
                req.symbol, req.start, req.end, resample="5min"
            )
        return self.market.load_minute_df(req.symbol, req.start, req.end)

    @staticmethod
    def _periods_per_year(period: str) -> float:
        """夏普年化因子。"""
        if period == "5m":
            return 252.0 * 48.0
        if period == "1m":
            return 252.0 * 240.0
        return 252.0

    def run(self, req: BacktestRequest, *, persist: bool = True) -> BacktestReport:
        """
        执行回测并可落库。

        @param req: 回测请求
        @param persist: 是否写入 BacktestRun（Walk-Forward 子段可关）
        @returns: 归一化报告
        """
        reg = self.registry.load(req.strategy_id)
        if not reg or not reg.on_bar:
            raise ValueError(f"strategy not found or not runnable: {req.strategy_id}")

        period = self._resolve_bar_period(req, reg)
        df = self._load_bars(req, period)
        if df.empty:
            hint = (
                "；分钟策略请先在行情同步中拉取该标的分钟线"
                if period in ("1m", "5m")
                else ""
            )
            raise ValueError(f"no bars for symbol/range{hint}")
        df = compute(df)
        history_df = df.copy()

        import yaml
        from desk_strategy.factor_rules import attach_ml_factor_columns, collect_factor_names

        body = getattr(reg.meta, "yaml_body", None) or ""
        parsed = yaml.safe_load(body) if body else None
        if isinstance(parsed, dict):
            history_df = attach_ml_factor_columns(
                history_df, collect_factor_names(parsed), self.db
            )

        df = df.set_index(pd.to_datetime(df["date"]))

        cerebro = bt.Cerebro()
        data = _PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.addstrategy(
            _SignalStrategy,
            desk_on_bar=reg.on_bar,
            symbol=req.symbol,
            history_df=history_df,
            db=self.db,
        )
        cerebro.addsizer(_ASharePercentSizer, percents=95.0)
        cerebro.broker.setcash(req.initial_cash)
        fee = get_settings()
        cerebro.broker.addcommissioninfo(
            AShareCommission(
                buy_commission=fee.backtest_buy_commission,
                sell_commission=fee.backtest_sell_commission,
                stamp_duty=fee.backtest_stamp_duty,
                min_commission=fee.backtest_min_commission,
            )
        )
        if fee.backtest_slippage and fee.backtest_slippage > 0:
            cerebro.broker.set_slippage_perc(fee.backtest_slippage)

        start_value = float(cerebro.broker.getvalue())
        result = cerebro.run()
        end_value = float(cerebro.broker.getvalue())
        strat = result[0]

        equity_curve = list(getattr(strat, "equity_curve", []) or [])
        if not equity_curve:
            equity_curve = [
                {"date": str(req.start), "value": start_value},
                {"date": str(req.end), "value": end_value},
            ]
        values = [float(p["value"]) for p in equity_curve]
        trade_list = list(getattr(strat, "trade_list", []) or [])
        closed_n = sum(1 for t in trade_list if t.get("status") != "open")
        total_return = (end_value / start_value) - 1.0 if start_value else 0.0
        max_drawdown = _max_drawdown_from_equity(values)
        sharpe = _sharpe_from_equity(
            values, periods_per_year=self._periods_per_year(period)
        )

        report = BacktestReport(
            strategy_id=req.strategy_id,
            symbol=req.symbol,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
            # 成交笔数仅计已平仓；未平仓见 trade_list.status=open
            trades=closed_n,
            equity_curve=_downsample_curve(equity_curve),
            trade_list=trade_list,
        )
        if persist:
            self.db.add(
                BacktestRun(
                    strategy_id=req.strategy_id,
                    symbol=req.symbol,
                    start_date=req.start,
                    end_date=req.end,
                    total_return=report.total_return,
                    max_drawdown=report.max_drawdown,
                    sharpe=report.sharpe,
                    trades=report.trades,
                    report_json=report.model_dump_json(),
                )
            )
            self.db.flush()
        return report
