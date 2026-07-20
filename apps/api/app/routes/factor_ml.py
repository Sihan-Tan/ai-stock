"""因子 / ML / 策略对比。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_backtest import BacktraderRunner
from desk_common.contracts import BacktestRequest
from desk_db import get_db
from desk_factor import FactorService
from desk_ml import MlTrainer

router = APIRouter()


class TrainIn(BaseModel):
    engine: str | None = None
    model_id: str | None = None


class CompareIn(BaseModel):
    strategy_ids: list[str]
    symbol: str = "600519.SH"
    start: date
    end: date
    initial_cash: float = 1_000_000.0


@router.get("/factors")
def factors():
    return {"factors": FactorService().list_factors()}


@router.get("/factors/series")
def factor_series(
    symbol: str,
    names: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    if not name_list:
        raise HTTPException(400, "names required")
    try:
        return FactorService(db).compute_series(symbol, name_list, start=start, end=end)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/ml/models")
def models(db: Session = Depends(get_db)):
    return MlTrainer(db).list_models()


@router.post("/ml/train-demo")
def train_demo(body: TrainIn, db: Session = Depends(get_db)):
    return MlTrainer(db).fit_demo(engine=body.engine, model_id=body.model_id)  # type: ignore[arg-type]


@router.post("/ml/compare-engines")
def compare_engines(db: Session = Depends(get_db)):
    """同数据集训练 LightGBM 与 XGBoost，返回指标对比。"""
    trainer = MlTrainer(db)
    a = trainer.fit_demo(engine="lightgbm", model_id="cmp_lgb")
    b = trainer.fit_demo(engine="xgboost", model_id="cmp_xgb")
    return {"lightgbm": a, "xgboost": b}


@router.post("/strategies/compare")
def compare_strategies(body: CompareIn, db: Session = Depends(get_db)):
    """多策略同区间回测对比。"""
    runner = BacktraderRunner(db)
    rows = []
    for sid in body.strategy_ids:
        try:
            report = runner.run(
                BacktestRequest(
                    strategy_id=sid,
                    symbol=body.symbol,
                    start=body.start,
                    end=body.end,
                    initial_cash=body.initial_cash,
                )
            )
            rows.append(report.model_dump())
        except Exception as exc:  # noqa: BLE001
            rows.append({"strategy_id": sid, "error": str(exc)})
    if not rows:
        raise HTTPException(400, "no strategies compared")
    return {"symbol": body.symbol, "results": rows}
