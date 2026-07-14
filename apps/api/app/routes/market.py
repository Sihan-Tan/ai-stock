"""行情 / 自选 / 板块。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_market import MarketService

router = APIRouter(prefix="/market")


class WatchIn(BaseModel):
    symbol: str
    name: str = ""


@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    svc = MarketService(db)
    svc.seed_demo_data()
    return {"ok": True}


@router.get("/watchlist")
def watchlist(db: Session = Depends(get_db)):
    return MarketService(db).list_watchlist()


@router.post("/watchlist")
def add_watch(body: WatchIn, db: Session = Depends(get_db)):
    return MarketService(db).add_watchlist(body.symbol, body.name)


@router.get("/boards")
def boards(board_type: str | None = None, db: Session = Depends(get_db)):
    return MarketService(db).list_boards(board_type)
