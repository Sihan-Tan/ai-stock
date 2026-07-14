"""策略管理。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_strategy import StrategyRegistry

router = APIRouter(prefix="/strategies")


class YamlIn(BaseModel):
    yaml_body: str


class DraftIn(BaseModel):
    payload: dict


@router.get("")
def list_strategies(source: str | None = None, db: Session = Depends(get_db)):
    return [m.model_dump() for m in StrategyRegistry(db).list(source)]


@router.post("/sync-python")
def sync_python(db: Session = Depends(get_db)):
    n = StrategyRegistry(db).sync_python_to_db()
    return {"synced": n}


@router.post("/from-yaml")
def from_yaml(body: YamlIn, db: Session = Depends(get_db)):
    meta = StrategyRegistry(db).from_yaml(body.yaml_body)
    return meta.model_dump()


@router.post("/load-yaml-file")
def load_file(db: Session = Depends(get_db)):
    candidates = [
        Path("configs/strategies/breakout.yaml"),
        Path(__file__).resolve().parents[4] / "configs" / "strategies" / "breakout.yaml",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        raise HTTPException(404, "yaml not found")
    return StrategyRegistry(db).load_yaml_file(path).model_dump()


@router.post("/draft")
def draft(body: DraftIn, db: Session = Depends(get_db)):
    return StrategyRegistry(db).save_agent_draft(body.payload).model_dump()


@router.post("/{strategy_id}/promote")
def promote(strategy_id: str, db: Session = Depends(get_db)):
    meta = StrategyRegistry(db).promote(strategy_id)
    if not meta:
        raise HTTPException(404, "not found")
    return meta.model_dump()
