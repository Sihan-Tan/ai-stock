"""告警。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_alert import FeishuWebhookChannel
from desk_db import get_db

router = APIRouter(prefix="/alerts")


class AlertIn(BaseModel):
    title: str
    body: str
    category: str = "signal"
    dedupe_key: str = ""


@router.get("")
def list_alerts(db: Session = Depends(get_db)):
    return FeishuWebhookChannel(db).list_recent()


@router.post("/send")
def send_alert(body: AlertIn, db: Session = Depends(get_db)):
    return FeishuWebhookChannel(db).send(body.title, body.body, body.category, body.dedupe_key)
