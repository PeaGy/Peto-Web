"""Create/version documents and export user-reviewed drafts."""
import io
import zipfile
from typing import Literal
from urllib.parse import quote
import anyio
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from features.accounts.auth import current_owner
from storage import documents as store
from features.documents.export import MAX_CONTENT, clean_text, image_numbers, parse_blocks
from features.documents.jobs import (EXPORT_WAIT, PREVIEW_WAIT, RenderBusy, build_presentation, build_spreadsheet, export_file,
                                     prepare_spreadsheet, render_page, render_queue)
from features.documents.sheets.view import grid as sheet_grid
from features.documents.tools import CHANGED_PREFIX, parse_changes
from features.documents.workbook_edit.package import EditError
from features.documents.workbook_grid import grid as workbook_grid
from features.documents.slides.spec import image_numbers as slide_images, load as load_deck
from features.documents import images as document_images

router = APIRouter(prefix='/api/documents', tags=['documents'])


class Draft(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=MAX_CONTENT)
    style: Literal['classic', 'band', 'minimal', 'essay', 'report'] = 'classic'


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
    return await store.save_document(owner, draft.conversation_id, title, content, style=draft.style)


@router.get('/{document_id}')
async def read(document_id: str, version: int | None = Query(None, ge=1), owner: str = Depends(current_owner)):
    return await store.get_document(owner, document_id, version)


@router.post('/{document_id}/versions')
async def revise(document_id: str, draft: Revision, owner: str = Depends(current_owner)):
    current = await store.get_document(owner, document_id)
    if current.get('format') == 'pptx':
        raise HTTPException(400, 'Bài thuyết trình chưa sửa tay được. Nhờ Peto sửa trong chat, Peto sẽ tạo phiên bản mới.')
    if current.get('format') == 'xlsx':
        raise HTTPException(400, 'Bảng tính chưa sửa tay được. Nhờ Peto sửa trong chat, Peto sẽ tạo phiên bản mới.')
    title, content = validate(draft)
    return await store.save_document(owner, None, title, content, document_id, draft.base_version, style=draft.style)


@router.delete('/{document_id}')
async def delete(document_id: str, owner: str = Depends(current_owner)):
    await store.delete_document(owner, document_id)
    return {'ok': True}


@router.get('/{document_id}/export/{format}')
async def export(document_id: str, format: Literal['docx', 'pdf', 'pptx', 'xlsx'], version: int = Query(ge=1), owner: str = Depends(current_owner)):
    draft = await store.get_document(owner, document_id, version)
    assets = await store.get_assets(owner, document_id, version)
    if draft.get('format') == 'pptx':
        return await export_presentation(owner, draft, assets, version, format)
    if draft.get('format') == 'xlsx':
        return await export_spreadsheet(draft, assets, version, format)
    if format in ('pptx', 'xlsx'):
        raise HTTPException(400, 'Tài liệu này không có bản PowerPoint.' if format == 'pptx' else 'Tài liệu này không có bản Excel.')
    if assets:
        data = assets[format]
        return file_response(draft, version, format, data)
    # One render per process on the small VPS; later requests wait briefly in a short queue (document_jobs.RenderQueue).
    try:
        numbers = image_numbers(parse_blocks(draft['content']))
        raw_images = await document_images.load(owner, draft['conversation_id'], numbers, strict=False)
        async with render_queue.slot(EXPORT_WAIT):
            data = await anyio.to_thread.run_sync(export_file, format, draft['title'], draft['content'], draft['style'], raw_images)
    except RenderBusy:
        raise HTTPException(429, 'Peto đang xuất tài liệu khác. Bạn thử lại sau vài giây nhé.') from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(422, 'Chưa xuất được bố cục này. Hãy chia bảng hoặc đoạn quá dài rồi thử lại.') from error
    return file_response(draft, version, format, data)


async def export_presentation(owner, draft, assets, version, format):
    """Bài thuyết trình tải PPTX hoặc bản PDF cùng bố cục; không có bản Word."""
    if format == 'docx':
        raise HTTPException(400, 'Bài thuyết trình chỉ tải được PPTX hoặc PDF.')
    if assets and assets.get(format):
        return file_response(draft, version, format, assets[format])
    try:
        raw_images = await document_images.load(owner, draft['conversation_id'], slide_images(load_deck(draft['content'])), strict=False)
        async with render_queue.slot(EXPORT_WAIT):
            files = await anyio.to_thread.run_sync(build_presentation, draft['content'], raw_images)
    except RenderBusy:
        raise HTTPException(429, 'Peto đang xuất tài liệu khác. Bạn thử lại sau vài giây nhé.') from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return file_response(draft, version, format, files[format])


async def export_spreadsheet(draft, assets, version, format):
    """Bảng tính chỉ tải được XLSX; dựng lại khi tệp đã lưu bị thiếu. Tệp Excel có macro (.xlsm) Peto đã sửa tải về
    đúng đuôi .xlsm, vì Excel không mở tệp có macro mang đuôi .xlsx."""
    if format != 'xlsx':
        raise HTTPException(400, 'Bảng tính chỉ tải được tệp XLSX.')
    if assets and assets.get('xlsx'):
        if macro_enabled(assets['xlsx']):
            return file_response(draft, version, 'xlsm', assets['xlsx'])
        return file_response(draft, version, format, assets['xlsx'])
    if draft.get('style') == 'workbook':
        raise HTTPException(404, 'Không còn tệp của bản sửa này.')
    try:
        async with render_queue.slot(EXPORT_WAIT):
            files = await anyio.to_thread.run_sync(build_spreadsheet, draft['content'])
    except RenderBusy:
        raise HTTPException(429, 'Peto đang xuất tài liệu khác. Bạn thử lại sau vài giây nhé.') from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return file_response(draft, version, format, files['xlsx'])


@router.get('/{document_id}/sheet')
async def sheet(document_id: str, version: int = Query(ge=1), owner: str = Depends(current_owner)):
    """Số liệu cho lưới xem bảng tính: chữ đã định dạng, công thức từng ô, biểu đồ. Tính lại từ nội dung đã lưu."""
    draft = await store.get_document(owner, document_id, version)
    if draft.get('format') != 'xlsx':
        raise HTTPException(404, 'Tài liệu này không phải bảng tính.')
    try:
        if draft.get('style') == 'workbook':
            # Tệp người dùng Peto đã sửa: lưới đọc thẳng từ tệp đã lưu, kèm ô đã sửa ghi trong nội dung.
            assets = await store.get_assets(owner, document_id, version)
            if not assets or not assets.get('xlsx'):
                raise HTTPException(404, 'Không còn tệp của bản sửa này.')
            changed = next((line[len(CHANGED_PREFIX):] for line in draft['content'].splitlines()
                            if line.startswith(CHANGED_PREFIX)), '')
            data = await anyio.to_thread.run_sync(workbook_grid, assets['xlsx'], draft['title'], changed)
            data['changes'] = parse_changes(draft['content'])
        else:
            data = await anyio.to_thread.run_sync(lambda: sheet_grid(prepare_spreadsheet(draft['content'])))
    except (ValueError, EditError) as error:
        raise HTTPException(422, f'Chưa đọc lại được bảng tính: {error}') from error
    return JSONResponse(data, headers={'Cache-Control': 'private, no-store'})


def macro_enabled(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return b'macroEnabled.main+xml' in archive.read('[Content_Types].xml')
    except (zipfile.BadZipFile, KeyError, OSError):
        return False


MIME = {
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xlsm': 'application/vnd.ms-excel.sheet.macroEnabled.12',
}


def file_response(draft, version, format, data):
    filename = ''.join(c for c in draft['title'] if c.isalnum() or c in ' -_').strip()[:90] or 'Tai lieu Peto'
    mime = MIME[format]
    return Response(data, media_type=mime, headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}-v{version}.{format}",
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.get('/{document_id}/preview')
async def preview(document_id: str, version: int = Query(ge=1), page: int = Query(1, ge=1, le=40), owner: str = Depends(current_owner)):
    assets = await store.get_assets(owner, document_id, version)
    if not assets or page > assets['pages'] or assets['format'] == 'xlsx':
        raise HTTPException(404, 'Không tìm thấy bản xem trước này.')
    if page == 1:
        data = assets['preview']
    else:
        try:
            async with render_queue.slot(PREVIEW_WAIT):
                data = await anyio.to_thread.run_sync(render_page, assets['pdf'], page)
        except RenderBusy:
            raise HTTPException(429, 'Đang xử lý tài liệu khác. Thử lại sau vài giây nhé.') from None
    return Response(data, media_type='image/png', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
