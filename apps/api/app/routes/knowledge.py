"""知识库。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from desk_db import get_db
from desk_knowledge import KnowledgeStore

router = APIRouter(prefix="/knowledge")

_MAX_UPLOAD_BYTES = 30 * 1024 * 1024
_ALLOWED_SUFFIXES = {".pdf", ".md", ".txt"}


class DocIn(BaseModel):
    title: str
    content: str
    tags: str = ""
    doc_type: str = "markdown"


class DocUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: str | None = None
    doc_type: str | None = None


class SearchIn(BaseModel):
    query: str
    top_k: int = 5
    mode: str | None = None


def _map_store_error(exc: Exception) -> HTTPException:
    """KeyError → 404；ValueError → 400。"""
    if isinstance(exc, KeyError):
        detail = exc.args[0] if exc.args else "文档不存在"
        return HTTPException(404, str(detail))
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    raise exc


@router.get("/docs")
def docs(db: Session = Depends(get_db)):
    return KnowledgeStore(db).list_docs()


@router.get("/docs/{doc_id}")
def get_doc(
    doc_id: str,
    full: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        return KnowledgeStore(db).get(doc_id, full=full)
    except (KeyError, ValueError) as exc:
        raise _map_store_error(exc) from exc


@router.post("/docs")
def create_doc(body: DocIn, db: Session = Depends(get_db)):
    try:
        return KnowledgeStore(db).create(body.title, body.content, body.doc_type, body.tags)
    except (KeyError, ValueError) as exc:
        raise _map_store_error(exc) from exc


@router.put("/docs/{doc_id}")
def update_doc(doc_id: str, body: DocUpdate, db: Session = Depends(get_db)):
    try:
        return KnowledgeStore(db).update(
            doc_id,
            title=body.title,
            content=body.content,
            tags=body.tags,
            doc_type=body.doc_type,
        )
    except (KeyError, ValueError) as exc:
        raise _map_store_error(exc) from exc


@router.delete("/docs/{doc_id}")
def delete_doc(doc_id: str, db: Session = Depends(get_db)):
    try:
        KnowledgeStore(db).delete(doc_id)
        return {"ok": True, "doc_id": doc_id}
    except (KeyError, ValueError) as exc:
        raise _map_store_error(exc) from exc


@router.post("/docs/upload")
async def upload_doc(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    tags: str | None = Form(None),
    db: Session = Depends(get_db),
):
    filename = file.filename or ""
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(400, "仅支持上传 .pdf / .md / .txt 文件")
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "文件大小不能超过 30MB")
    try:
        return KnowledgeStore(db).create_from_bytes(
            title or "",
            raw,
            filename,
            tags=tags or "",
        )
    except (KeyError, ValueError) as exc:
        raise _map_store_error(exc) from exc


@router.post("/search")
def search(body: SearchIn, db: Session = Depends(get_db)):
    try:
        return KnowledgeStore(db).search(body.query, body.top_k, mode=body.mode)
    except (KeyError, ValueError) as exc:
        raise _map_store_error(exc) from exc
