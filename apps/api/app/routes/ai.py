"""投研对话（nanobot）。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_ai import NanobotResearchSession, SkillLoader
from desk_db import get_db

router = APIRouter(prefix="/ai")


class ChatIn(BaseModel):
    messages: list[dict]


@router.get("/skills")
def skills():
    return SkillLoader().list()


@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db)):
    session = NanobotResearchSession(db)

    async def gen():
        async for chunk in session.run(body.messages):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
