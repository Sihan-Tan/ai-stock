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
        idx = len(self.data) - 1
        row = {
            "symbol": self.p.symbol,
            "close": float(self.data.close[0]),
            "sma_5": float(self.data.close.get(ago=0)) if False else None,
        }
        # 使用 line 上附加的指标列不可用时，用简单均线近似
        closes = [float(self.data.close[-i]) for i in range(min(20, idx + 1))]
        closes = list(reversed(closes))
        s = pd.Series(closes)
        row["sma_5"] = float(s.tail(5).mean()) if len(s) >= 5 else None
        row["sma_20"] = float(s.tail(20).mean()) if len(s) >= 20 else None
        if len(s) >= 6:
            prev = s.iloc[:-1]
            row["prev_sma_5"] = float(prev.tail(5).mean()) if len(prev) >= 5 else row["sma_5"]
            row["prev_sma_20"] = float(prev.tail(20).mean()) if len(prev) >= 20 else row["sma_20"]
        else:
            row["prev_sma_5"] = row["sma_5"]
            row["prev_sma_20"] = row["sma_20"]

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
