"""Sửa ảnh: truyền ảnh gốc, lưu riêng kết quả, quyền truy cập và nâng cấp dữ liệu."""
import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest

import auth
import db
import imagine_api
from ai import imagine
from config import SESSION_COOKIE, UPLOAD_DIR, owner_key

PNG = imagine._MOCK_PNG
UPLOAD = {"data": base64.b64encode(PNG).decode("ascii")}


async def test_upload_edits_and_saves_source_separately(client, monkeypatch):
    provider = AsyncMock(return_value=[imagine.GeneratedImage(PNG, "image/png")] * 2)
    monkeypatch.setattr(imagine_api, "generate_images", provider)
    response = await client.post("/api/imagine", json={"prompt": "Đổi nền xanh", "source_image": UPLOAD, "n": 2})
    assert response.status_code == 200
    assert provider.call_args.kwargs["source_image"] == imagine.GeneratedImage(PNG, "image/png")
    job = response.json()["job"]
    assert len(job["images"]) == 2
    assert job["source_image"]["id"] not in [image["id"] for image in job["images"]]
    assert (await client.get(job["source_image"]["url"])).content == PNG
    listed = next(row for row in (await client.get("/api/imagine")).json()["jobs"] if row["id"] == job["id"])
    assert listed["source_image"] == job["source_image"]
    assert len(listed["images"]) == 2


async def test_edit_existing_image_preserves_original_and_copies_source(client):
    original = (await client.post("/api/imagine", json={"prompt": "mèo trắng"})).json()["job"]
    original_image = original["images"][0]
    edited = (await client.post("/api/imagine", json={"prompt": "Thêm mũ tím", "source_image_id": original_image["id"]})).json()["job"]
    assert edited["id"] != original["id"]
    assert edited["source_image"]["id"] != original_image["id"]
    assert (await client.get(original_image["url"])).content == PNG
    # Xóa lượt cũ không làm mất ảnh gốc đã chụp lại cho lượt sửa mới.
    assert (await client.delete(f"/api/imagine/{original['id']}")).status_code == 200
    assert (await client.get(edited["source_image"]["url"])).content == PNG
    assert (await client.get(edited["images"][0]["url"])).status_code == 200


async def test_source_and_edit_request_are_private(client, monkeypatch):
    job = (await client.post("/api/imagine", json={"prompt": "ảnh riêng", "source_image": UPLOAD})).json()["job"]
    client.cookies.set(SESSION_COOKIE, auth._sign(owner_key("discord", "333333333333333333")))
    provider = AsyncMock()
    monkeypatch.setattr(imagine_api, "generate_images", provider)
    for image in [job["source_image"], *job["images"]]:
        assert (await client.get(image["url"])).status_code == 404
        response = await client.post("/api/imagine", json={"prompt": "sửa", "source_image_id": image["id"]})
        assert response.status_code == 404
    provider.assert_not_called()


async def test_delete_edit_removes_source_and_outputs(client):
    job = (await client.post("/api/imagine", json={"prompt": "đổi màu", "source_image": UPLOAD})).json()["job"]
    folder = Path(UPLOAD_DIR) / "imagine" / job["id"]
    assert len(list(folder.iterdir())) == 2
    assert (await client.delete(f"/api/imagine/{job['id']}")).status_code == 200
    assert not folder.exists()
    for image in [job["source_image"], *job["images"]]:
        assert (await client.get(image["url"])).status_code == 404


@pytest.mark.parametrize("extra", [
    {"source_image": {"data": "không phải base64"}},
    {"source_image": {"data": base64.b64encode(b"<html>khong phai anh</html>").decode()}},
    {"source_image": {"data": base64.b64encode(b"GIF89a0123456789").decode()}},
    {"source_image": UPLOAD, "source_image_id": "ca-hai"},
])
async def test_bad_source_rejected_before_ai_call(client, monkeypatch, extra):
    provider = AsyncMock()
    monkeypatch.setattr(imagine_api, "generate_images", provider)
    before = (await client.get("/api/imagine")).json()["jobs"]
    response = await client.post("/api/imagine", json={"prompt": "sửa ảnh", **extra})
    assert response.status_code == 400
    provider.assert_not_called()
    assert (await client.get("/api/imagine")).json()["jobs"] == before


async def test_source_size_is_checked_server_side(client, monkeypatch):
    monkeypatch.setattr(imagine_api, "MAX_IMAGINE_SOURCE_BYTES", 16)
    response = await client.post("/api/imagine", json={"prompt": "sửa", "source_image": UPLOAD})
    assert response.status_code == 400


async def test_missing_saved_source_is_readable_error(client):
    response = await client.post("/api/imagine", json={"prompt": "sửa", "source_image_id": "khong-ton-tai"})
    assert response.status_code == 404
    assert "ảnh gốc" in response.json()["detail"]


async def test_edit_provider_uses_json_edit_endpoint_with_real_image(monkeypatch):
    sent = []

    def handle(request):
        sent.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": UPLOAD["data"]}]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(imagine, "AI_PROVIDER", "xai")
    monkeypatch.setattr(imagine.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(imagine.XaiAuth, "get_access_token", AsyncMock(return_value="token-gia"))
    result = await imagine.generate_images(prompt="đổi nền", quality="medium", resolution="2k", aspect_ratio="auto", n=1, source_image=imagine.GeneratedImage(PNG, "image/png"))
    assert sent[0].url.path.endswith("/images/edits")
    assert sent[0].headers["content-type"] == "application/json"
    payload = json.loads(sent[0].content)
    assert payload["image"] == {"type": "image_url", "url": "data:image/png;base64," + UPLOAD["data"]}
    assert payload["model"] == imagine.IMAGINE_MODEL
    assert payload["quality"] == "medium" and payload["resolution"] == "2k"
    assert result[0].data == PNG


async def test_migration_keeps_old_images_as_outputs(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    async with aiosqlite.connect(path) as connection:
        await connection.execute("CREATE TABLE imagine_images (id TEXT PRIMARY KEY, job_id TEXT, owner TEXT, mime TEXT, path TEXT, created_at REAL)")
        await connection.execute("INSERT INTO imagine_images VALUES ('cu', 'luot-cu', 'nguoi-cu', 'image/png', 'anh-cu.png', 1)")
        await connection.commit()
    await db.init_db()
    await db.init_db()
    async with aiosqlite.connect(path) as connection:
        row = await (await connection.execute("SELECT id, kind FROM imagine_images")).fetchone()
    assert row == ("cu", "output")
