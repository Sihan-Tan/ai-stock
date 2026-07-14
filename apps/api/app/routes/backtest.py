"""回测。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from desk_backtest import BacktraderRunner
from desk_common.contracts import BacktestRequest
from desk_db import get_db

router = APIRouter(prefix="/backtest")


@router.post("/run")
def run_bt(req: BacktestRequest, db: Session = Depends(get_db)):
    try:
        report = BacktraderRunner(db).run(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return report.model_dump()
