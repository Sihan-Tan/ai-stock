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
    skill_hint: str | None = None


@router.get("/skills")
def skills():
    return SkillLoader().list()


@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db)):
    session = NanobotResearchSession(db)

    async def gen():
        try:
            async for chunk in session.run(body.messages, skill_hint=body.skill_hint):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            # 兜底：避免未捕获异常直接掐断 SSE/流式连接
            yield NanobotResearchSession._format_llm_error(exc)

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.get("/financials/{symbol}")
def financials(symbol: str, years: int = 5, db: Session = Depends(get_db)):
    from desk_market.financials import FinancialService

    return FinancialService(db).get_financials(symbol, years=years)
