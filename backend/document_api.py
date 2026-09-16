"""Create/version documents and export user-reviewed drafts."""
import asyncio
from typing import Literal
from urllib.parse import quote
import anyio
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from auth import current_owner
import document_store as store
from document_export import MAX_CONTENT, clean_text, parse_blocks, render_docx, render_pdf

router = APIRouter(prefix='/api/documents', tags=['documents'])
_render_lock = asyncio.Lock()


class Draft(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=MAX_CONTENT)


class NewDocument(Draft):
    conversation_id: str = Field(min_length=1, max_length=64)


class Revision(Draft):
    base_version: int = Field(ge=1, le=store.MAX_VERSIONS)


def validate(draft):
    title = ' '.join(clean_text(draft.title).split())
    content = clean_text(draft.content)
    if not title: raise HTTPException(400, 'Hãy nhập tên tài liệu.')
    try: parse_blocks(content)
    except ValueError as error: raise HTTPException(400, str(error)) from error
    return title, content


@router.get('')
async def listing(conversation_id: str = Query(max_length=64), owner: str = Depends(current_owner)):
    return {'documents': await store.list_documents(owner, conversation_id)}


@router.post('')
async def create(draft: NewDocument, owner: str = Depends(current_owner)):
    title, content = validate(draft)
    return await store.save_document(owner, draft.conversation_id, title, content)


@router.get('/{document_id}')
async def read(document_id: str, version: int | None = Query(None, ge=1), owner: str = Depends(current_owner)):
    return await store.get_document(owner, document_id, version)


@router.post('/{document_id}/versions')
async def revise(document_id: str, draft: Revision, owner: str = Depends(current_owner)):
    title, content = validate(draft)
    return await store.save_document(owner, None, title, content, document_id, draft.base_version)


@router.delete('/{document_id}')
async def delete(document_id: str, owner: str = Depends(current_owner)):
    await store.delete_document(owner, document_id)
    return {'ok': True}


@router.get('/{document_id}/export/{format}')
async def export(document_id: str, format: Literal['docx', 'pdf'], version: int = Query(ge=1), owner: str = Depends(current_owner)):
    draft = await store.get_document(owner, document_id, version)
    # One export per process: avoid a queue of CPU-heavy jobs on the small VPS.
    if _render_lock.locked(): raise HTTPException(429, 'Peto đang xuất tài liệu khác. Bạn thử lại sau vài giây nhé.')
    async with _render_lock:
        try:
            data = await anyio.to_thread.run_sync(render_pdf if format == 'pdf' else render_docx, draft['title'], draft['content'])
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except Exception as error:
            raise HTTPException(422, 'Chưa xuất được bố cục này. Hãy chia bảng hoặc đoạn quá dài rồi thử lại.') from error
    filename = ''.join(c for c in draft['title'] if c.isalnum() or c in ' -_').strip()[:90] or 'Tai lieu Peto'
    mime = 'application/pdf' if format == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return Response(data, media_type=mime, headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}-v{version}.{format}",
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
    })
