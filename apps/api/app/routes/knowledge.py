"""知识库。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_knowledge import KnowledgeStore

router = APIRouter(prefix="/knowledge")


class DocIn(BaseModel):
    title: str
    content: str
    tags: str = ""
    doc_type: str = "markdown"


class SearchIn(BaseModel):
    query: str
    top_k: int = 5


@router.get("/docs")
def docs(db: Session = Depends(get_db)):
    return KnowledgeStore(db).list_docs()


@router.post("/docs")
def upsert(body: DocIn, db: Session = Depends(get_db)):
    return KnowledgeStore(db).upsert(body.title, body.content, body.doc_type, body.tags)


@router.post("/search")
def search(body: SearchIn, db: Session = Depends(get_db)):
    return KnowledgeStore(db).search(body.query, body.top_k)
