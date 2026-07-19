"""投研对话（nanobot）。"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from desk_ai import NanobotResearchSession, SkillLoader
from desk_db import get_db

router = APIRouter(prefix="/ai")


class ChatIn(BaseModel):
    messages: list[dict]
    skill_hint: str | None = None
    enabled_skills: list[str] | None = Field(
        default=None,
        description="勾选启用的 skill 名；空列表表示不加载任何 skill 正文",
    )


@router.get("/skills")
def skills():
    return SkillLoader().list()


@router.get("/skills/{name}")
def skill_detail(name: str):
    """返回单个 skill 的描述与全文。"""
    loader = SkillLoader()
    items = {i["name"]: i for i in loader.list()}
    meta = items.get(name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {name}")
    try:
        content = loader.load(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "name": name,
        "description": meta.get("description") or "",
        "content": content,
    }


@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db)):
    session = NanobotResearchSession(db)

    async def gen():
        try:
            async for chunk in session.run(
                body.messages,
                skill_hint=body.skill_hint,
                enabled_skills=body.enabled_skills,
            ):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            # 兜底：避免未捕获异常直接掐断 SSE/流式连接
            yield NanobotResearchSession._format_llm_error(exc)

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.get("/financials/{symbol}")
def financials(symbol: str, years: int = 5, db: Session = Depends(get_db)):
    from desk_market.financials import FinancialService

    return FinancialService(db).get_financials(symbol, years=years)
