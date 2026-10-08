"""Lịch sử thuộc ảnh chính: lưu bền, phân nhánh và cách ly tài khoản."""
import asyncio
import base64
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

from ai import imagine
from features.imagine import api
import storage as db
from conftest import sign_in


def revision(operation="crop"):
    return {"data": base64.b64encode(imagine._MOCK_PNG).decode(), "operation": operation, "request_id": uuid.uuid4().hex}


async def test_local_revisions_branch_persist_and_stay_out_of_library(client, monkeypatch):
    owner = await sign_in(client)
    root = (await client.post('/api/imagine', json={"prompt": "ảnh chính", "n": 2})).json()['job']
    image_id = root['images'][0]['id']
    provider = AsyncMock()
    monkeypatch.setattr(api, 'generate_images', provider)
    body = revision()
    child = (await client.post(f'/api/imagine/images/{image_id}/revisions', json=body)).json()['job']
    again = (await client.post(f'/api/imagine/images/{image_id}/revisions', json=body)).json()['job']
    assert child == again
    assert child['root_image_id'] == image_id and child['edit_parent_image_id'] == image_id
    child_id = child['images'][0]['id']
    grandchild = (await client.post(f'/api/imagine/images/{child_id}/revisions', json=revision('brush'))).json()['job']
    branch = (await client.post(f'/api/imagine/images/{image_id}/revisions', json=revision())).json()['job']
    assert grandchild['edit_parent_image_id'] == child_id
    assert branch['edit_parent_image_id'] == image_id
    assert len((await client.get('/api/imagine')).json()['jobs']) == 1
    workspace = (await client.get(f'/api/imagine/images/{grandchild["images"][0]["id"]}/workspace')).json()
    assert workspace['root_image_id'] == image_id
    assert [job['id'] for job in workspace['jobs']] == [child['id'], grandchild['id'], branch['id']]
    assert (await client.get(f'/api/imagine/images/{root["images"][1]["id"]}/workspace')).json()['jobs'] == []
    assert await db.get_imagine_workspace(owner, image_id)  # Đọc lại từ SQLite, không dựa vào bộ nhớ API.
    assert (await client.post(f'/api/imagine/images/{image_id}/revisions', json={**body, 'operation': 'brush'})).status_code == 409
    provider.assert_not_awaited()


async def test_ai_revision_pending_receipt_and_cascade_cleanup(client, monkeypatch):
    owner = await sign_in(client)
    root = (await client.post('/api/imagine', json={"prompt": "ảnh chính"})).json()['job']
    image_id = root['images'][0]['id']
    child = (await client.post(f'/api/imagine/images/{image_id}/revisions', json=revision())).json()['job']
    child_id = child['images'][0]['id']
    release = asyncio.Event()
    async def generate(**kwargs):
        await release.wait()
        return [imagine.GeneratedImage(imagine._MOCK_PNG, 'image/png')]
    provider = AsyncMock(side_effect=generate)
    monkeypatch.setattr(api, 'generate_images', provider)
    body = {"prompt": "sửa tiếp", "source_image_id": child_id, "edit_parent_image_id": child_id,
            "background": True, "request_id": uuid.uuid4().hex}
    try:
        response = await client.post('/api/imagine', json=body)
        assert response.status_code == 202
        edited = response.json()['job']
        assert edited['root_image_id'] == image_id and edited['edit_parent_image_id'] == child_id
        assert (await client.post('/api/imagine', json=body)).json()['job']['id'] == edited['id']
        listed = (await client.get('/api/imagine')).json()
        assert len(listed['jobs']) == 1 and listed['active_edits'][0]['id'] == edited['id']
        assert (await client.delete(f'/api/imagine/images/{image_id}')).status_code == 409
        assert (await client.delete(f'/api/imagine/{root["id"]}')).status_code == 409
    finally:
        release.set()
        if api._tasks:
            await asyncio.gather(*list(api._tasks))
    provider.assert_awaited_once()
    workspace = (await client.get(f'/api/imagine/images/{image_id}/workspace')).json()
    assert len(workspace['jobs']) == 2
    ids = [image_id] + [image['id'] for job in workspace['jobs'] for image in job['images']]
    paths = [Path((await db.get_imagine_image(owner, image))['path']) for image in ids]
    assert all(path.exists() for path in paths)
    assert (await client.delete(f'/api/imagine/images/{image_id}')).status_code == 200
    assert all(not path.exists() for path in paths)
    for image in ids:
        assert (await client.get(f'/api/imagine/images/{image}')).status_code == 404
    assert (await client.post('/api/imagine', json=body)).status_code == 410
    provider.assert_awaited_once()


async def test_revision_ownership_and_parent_validation_before_provider(client, monkeypatch):
    await sign_in(client)
    root = (await client.post('/api/imagine', json={"prompt": "ảnh riêng", "n": 2})).json()['job']
    image_id = root['images'][0]['id']
    provider = AsyncMock()
    monkeypatch.setattr(api, 'generate_images', provider)
    assert (await client.post('/api/imagine', json={"prompt": "sửa", "source_image_id": root['images'][1]['id'], 'edit_parent_image_id': image_id})).status_code == 400
    await sign_in(client)
    assert (await client.get(f'/api/imagine/images/{image_id}/workspace')).status_code == 404
    assert (await client.post(f'/api/imagine/images/{image_id}/revisions', json=revision())).status_code == 404
    assert (await client.post('/api/imagine', json={"prompt": "sửa", "source_image_id": image_id, 'edit_parent_image_id': image_id})).status_code == 404
    provider.assert_not_awaited()


async def test_deleting_one_root_keeps_sibling_and_old_edits_independent(client):
    await sign_in(client)
    root = (await client.post('/api/imagine', json={"prompt": "hai ảnh", "n": 2})).json()['job']
    ids = [image['id'] for image in root['images']]
    for image_id in ids:
        await client.post(f'/api/imagine/images/{image_id}/revisions', json=revision())
    old_edit = (await client.post('/api/imagine', json={"prompt": "ảnh độc lập", "source_image_id": ids[0]})).json()['job']
    assert (await client.delete(f'/api/imagine/images/{ids[0]}')).json()['job_deleted'] is False
    assert len((await client.get(f'/api/imagine/images/{ids[1]}/workspace')).json()['jobs']) == 1
    assert (await client.get(old_edit['source_image']['url'])).status_code == 200
    assert (await client.delete(f'/api/imagine/{root["id"]}')).status_code == 200
    assert (await client.get(f'/api/imagine/images/{ids[1]}/workspace')).status_code == 404
