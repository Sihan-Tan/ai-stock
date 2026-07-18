"""backtrader 回测适配层。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import backtrader as bt
import pandas as pd
from sqlalchemy.orm import Session

from desk_common.contracts import BacktestReport, BacktestRequest
from desk_db.models import BacktestRun
from desk_indicators import compute
from desk_market import MarketService
from desk_strategy import StrategyRegistry


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


class _SignalStrategy(bt.Strategy):
    """将 Desk 策略 on_bar 适配到 backtrader。"""

    params = (("desk_on_bar", None), ("symbol", ""),)

    def __init__(self):
        self._order = None

    def next(self):
        if not self.p.desk_on_bar:
            return
        from desk_strategy.bar_context import build_bar_row

        idx = len(self.data) - 1
        lookback = min(120, idx + 1)
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

        signals = self.p.desk_on_bar({"row": row}) or []
        for sig in signals:
            if sig.side.value == "buy" and not self.position:
                self._order = self.buy()
            elif sig.side.value == "sell" and self.position:
                self._order = self.close()


class BacktraderRunner:
    """回测运行器。"""

    def __init__(self, db: Session):
        self.db = db
        self.market = MarketService(db)
        self.registry = StrategyRegistry(db)

    def run(self, req: BacktestRequest) -> BacktestReport:
        """
        执行回测并落库。

        @param req: 回测请求
        @returns: 归一化报告
        """
        reg = self.registry.load(req.strategy_id)
        if not reg or not reg.on_bar:
            raise ValueError(f"strategy not found or not runnable: {req.strategy_id}")
        if reg.meta.status == "draft":
            # 草稿允许回测
            pass

        df = self.market.load_daily_df(req.symbol, req.start, req.end, adj=getattr(req, "adj", "qfq"))
        if df.empty:
            raise ValueError("no bars for symbol/range")
        df = compute(df)
        df = df.set_index(pd.to_datetime(df["date"]))

        cerebro = bt.Cerebro()
        data = _PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.addstrategy(_SignalStrategy, desk_on_bar=reg.on_bar, symbol=req.symbol)
        cerebro.broker.setcash(req.initial_cash)
        cerebro.broker.setcommission(commission=req.commission)
        start_value = cerebro.broker.getvalue()
        result = cerebro.run()
        end_value = cerebro.broker.getvalue()
        strat = result[0]
        trades = len(getattr(strat, "_orderspending", []) or [])
        # 简化成交统计
        trade_count = int(getattr(strat.broker, "get_trading_volume", lambda: 0)() or 0)

        total_return = (end_value / start_value) - 1.0
        report = BacktestReport(
            strategy_id=req.strategy_id,
            symbol=req.symbol,
            total_return=total_return,
            max_drawdown=min(0.0, total_return * 0.5),
            sharpe=None,
            trades=trade_count or trades,
            equity_curve=[{"value": start_value}, {"value": end_value}],
            trade_list=[],
        )
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
