"""API dự án và tài liệu chỉ của tài khoản đã đăng nhập."""
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from features.accounts.auth import current_owner
from features.chat.schemas import AttachmentIn
from features.documents.reader import read_document, public_document
from shared.attachments import validate_batch, AttachmentError
from storage import projects

router = APIRouter(prefix='/api/projects')

class CreateProject(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class UpdateProject(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    instructions: str | None = Field(default=None, max_length=8000)

@router.get('')
async def list_all(owner=Depends(current_owner)):
    return {'projects': await projects.list_projects(owner)}

@router.post('')
async def create(body: CreateProject, owner=Depends(current_owner)):
    return await projects.create_project(owner, body.name)

@router.get('/{project_id}')
async def detail(project_id: str, owner=Depends(current_owner)):
    project = await projects.get_project(owner, project_id)
    files = await projects.list_files(owner, project_id)
    for file in files:
        file['document'] = public_document(file['document'])
        file['url'] = f"/api/projects/{project_id}/files/{file['id']}"
    return {**project, 'files': files}

@router.patch('/{project_id}')
async def update(project_id: str, body: UpdateProject, owner=Depends(current_owner)):
    await projects.update_project(owner, project_id, body.name, body.instructions)
    return {'updated': True}

@router.delete('/{project_id}')
async def delete(project_id: str, owner=Depends(current_owner)):
    await projects.delete_project(owner, project_id)
    return {'deleted': True}

@router.post('/{project_id}/files')
async def upload(project_id: str, body: AttachmentIn, owner=Depends(current_owner)):
    await projects.get_project(owner, project_id)
    try:
        file = validate_batch([body.model_dump()])[0]
    except AttachmentError as error:
        raise HTTPException(400, str(error)) from None
    if file.kind == 'image':
        raise HTTPException(400, 'Tài liệu dự án nhận PDF, DOCX, Excel (.xlsx) và tệp chữ/code; ảnh có thể gửi trong hội thoại')
    await projects.check_file_capacity(owner, project_id, len(file.data))
    document = await read_document(file.data, file.mime)
    file_id = await projects.add_file(owner, project_id, file, document)
    return {'id': file_id}

@router.get('/{project_id}/files/{file_id}')
async def download(project_id: str, file_id: str, owner=Depends(current_owner)):
    file = await projects.get_file(owner, project_id, file_id, data=True)
    return Response(file['data'], media_type=file['mime'], headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(file['name']),
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
    })

@router.delete('/{project_id}/files/{file_id}')
async def remove_file(project_id: str, file_id: str, owner=Depends(current_owner)):
    await projects.delete_file(owner, project_id, file_id)
    return {'deleted': True}
