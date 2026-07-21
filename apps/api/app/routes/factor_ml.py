"""因子 / ML / 策略对比。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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


class TrainSymbolsIn(BaseModel):
    """多股真实日线训练入参。"""

    symbols: list[str] = Field(min_length=1)
    start: date
    end: date
    engines: list[str] | None = None


class CompareIn(BaseModel):
    strategy_ids: list[str]
    symbol: str = "600519.SH"
    start: date
    end: date
    initial_cash: float = 1_000_000.0


class AsFactorIn(BaseModel):
    """标记模型是否出现在因子目录。"""

    as_factor: bool


@router.get("/factors")
def factors(db: Session = Depends(get_db)):
    return {"factors": FactorService(db).list_factors()}


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


@router.delete("/ml/models/{model_id}")
def delete_model(model_id: str, db: Session = Depends(get_db)):
    try:
        MlTrainer(db).delete_model(model_id)
        db.commit()
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True, "model_id": model_id}


@router.post("/ml/models/{model_id}/as-factor")
def set_as_factor(model_id: str, body: AsFactorIn, db: Session = Depends(get_db)):
    try:
        out = MlTrainer(db).set_as_factor(model_id, body.as_factor)
        db.commit()
        return out
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/ml/train-demo")
def train_demo(body: TrainIn, db: Session = Depends(get_db)):
    return MlTrainer(db).fit_demo(engine=body.engine, model_id=body.model_id)  # type: ignore[arg-type]


@router.post("/ml/train-symbols")
def train_symbols(body: TrainSymbolsIn, db: Session = Depends(get_db)):
    """
    用指定股票池的本地日线训练；默认同时跑 LightGBM 与 XGBoost。
    """
    if body.start > body.end:
        raise HTTPException(400, "start 不能晚于 end")
    engines = body.engines or ["lightgbm", "xgboost"]
    trainer = MlTrainer(db)
    try:
        if set(engines) >= {"lightgbm", "xgboost"} and len(engines) >= 2:
            return trainer.compare_engines_on_symbols(body.symbols, body.start, body.end)
        out: dict = {}
        for eng in engines:
            mid = f"sym_{eng}"
            out[eng] = trainer.fit_symbols(
                body.symbols,
                body.start,
                body.end,
                engine=eng,  # type: ignore[arg-type]
                model_id=mid,
            )
        return out
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/ml/compare-engines")
def compare_engines(db: Session = Depends(get_db)):
    """同数据集训练 LightGBM 与 XGBoost（合成 demo，兼容旧调用）。"""
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
