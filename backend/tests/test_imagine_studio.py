"""Nhiều ảnh, thứ tự, lịch sử và lượt tạo bền vững — không gọi dịch vụ thật."""
import asyncio
import base64
import io
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

import storage as db
from ai import imagine
from features.imagine import api
from conftest import sign_in


def upload(color: str = "red") -> dict:
    output = io.BytesIO()
    Image.new("RGB", (2, 3), color).save(output, format="PNG")
    return {"data": base64.b64encode(output.getvalue()).decode()}


async def wait_tasks():
    if api._tasks:
        await asyncio.wait_for(asyncio.gather(*list(api._tasks)), 2)


async def test_mixed_sources_keep_order_ancestry_and_independent_copies(client, monkeypatch):
    await sign_in(client)
    first = (await client.post("/api/imagine", json={"prompt": "ảnh cũ"})).json()["job"]
    refs = [upload("blue"), {"image_id": first["images"][0]["id"]}, upload("green")]
    provider = AsyncMock(return_value=[imagine.GeneratedImage(imagine._MOCK_PNG, "image/png")])
    monkeypatch.setattr(api, "generate_images", provider)
    response = await client.post("/api/imagine", json={"prompt": "ghép ảnh 1 và 2", "source_images": refs})
    assert response.status_code == 200
    job = response.json()["job"]
    sources = job["source_images"]
    assert len(sources) == 3 and job["source_image"] == sources[0]
    assert provider.call_args.kwargs["source_images"][0].data == base64.b64decode(refs[0]["data"])
    assert sources[1]["parent_job_id"] == first["id"]
    assert sources[1]["parent_image_id"] == first["images"][0]["id"]
    listed = (await client.get("/api/imagine")).json()["jobs"][0]
    assert listed["source_images"] == sources
    await client.delete(f"/api/imagine/{first['id']}")
    for index, ref in enumerate(refs):
        expected = base64.b64decode(ref["data"]) if "data" in ref else imagine._MOCK_PNG
        assert (await client.get(sources[index]["url"])).content == expected


@pytest.mark.parametrize("refs,extra", [
    ([upload()] * 6, {}), ([{}], {}), ([{**upload(), "image_id": "id"}], {}),
    ([upload()], {"source_image": upload()}),
    ([{"data": base64.b64encode(b"\x89PNG\r\n\x1a\nnot-an-image").decode()}], {}),
])
async def test_bad_multi_input_never_calls_provider(client, monkeypatch, refs, extra):
    await sign_in(client)
    provider = AsyncMock()
    monkeypatch.setattr(api, "generate_images", provider)
    response = await client.post("/api/imagine", json={"prompt": "sửa", "source_images": refs, **extra})
    assert response.status_code in {400, 422}
    provider.assert_not_awaited()
    assert (await client.get("/api/imagine")).json()["jobs"] == []


async def test_five_sources_and_new_ratios(client):
    await sign_in(client)
    response = await client.post("/api/imagine", json={"prompt": "sửa", "source_images": [upload()] * 5, "aspect_ratio": "21:9"})
    assert response.status_code == 200
    assert len(response.json()["job"]["source_images"]) == 5


async def test_total_bytes_and_streamed_body_limit(client, monkeypatch):
    await sign_in(client)
    provider = AsyncMock()
    monkeypatch.setattr(api, "generate_images", provider)
    monkeypatch.setattr(api, "MAX_SOURCE_TOTAL_BYTES", len(base64.b64decode(upload()["data"])) * 2 - 1)
    response = await client.post("/api/imagine", json={"prompt": "sửa", "source_images": [upload()] * 2})
    assert response.status_code == 400
    monkeypatch.setattr(api, "MAX_REQUEST_BYTES", 30)
    async def chunks():
        yield b'{"prompt":"'
        yield b'x' * 40
        yield b'"}'
    response = await client.post("/api/imagine", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    provider.assert_not_awaited()


async def test_provider_uses_ordered_json_images(client, monkeypatch):
    seen = []
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            seen.append((url, kwargs["json"]))
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(imagine._MOCK_PNG).decode()}]})
    monkeypatch.setattr(imagine, "AI_PROVIDER", "xai")
    monkeypatch.setattr(imagine.XaiAuth, "get_access_token", AsyncMock(return_value="fake"))
    monkeypatch.setattr(imagine.httpx, "AsyncClient", FakeClient)
    sources = [imagine.GeneratedImage(base64.b64decode(upload(color)["data"]), "image/png") for color in ["red", "blue"]]
    await imagine.generate_images(prompt="ghép", quality="medium", resolution="1k", aspect_ratio="auto", n=1, source_images=sources)
    url, payload = seen[0]
    assert url.endswith("/images/edits") and "image" not in payload
    assert [base64.b64decode(item["url"].split(",")[1]) for item in payload["images"]] == [image.data for image in sources]


async def test_background_survives_response_and_deduplicates(client, monkeypatch):
    await sign_in(client)
    release = asyncio.Event()
    async def generate(**kwargs):
        await release.wait()
        return [imagine.GeneratedImage(imagine._MOCK_PNG, "image/png")]
    provider = AsyncMock(side_effect=generate)
    monkeypatch.setattr(api, "generate_images", provider)
    request = {"prompt": "chờ", "background": True, "request_id": uuid.uuid4().hex, "source_images": [upload()]}
    try:
        created = await client.post("/api/imagine", json=request)
        assert created.status_code == 202
        job = created.json()["job"]
        duplicate = await client.post("/api/imagine", json=request)
        assert duplicate.json()["job"]["id"] == job["id"]
        assert (await client.post("/api/imagine", json={**request, "prompt": "khác"})).status_code == 409
        assert (await client.post("/api/imagine", json={**request, "request_id": uuid.uuid4().hex})).status_code == 429
        assert (await client.delete(f"/api/imagine/{job['id']}")).status_code == 409
        restored = (await client.get(f"/api/imagine/requests/{request['request_id']}")).json()["job"]
        assert restored["id"] == job["id"] and restored["status"] in {"queued", "running"}
    finally:
        release.set()
        await wait_tasks()
    complete = (await client.get(f"/api/imagine/{job['id']}")).json()["job"]
    assert complete["status"] == "complete" and len(complete["images"]) == 1
    provider.assert_awaited_once()


async def test_simultaneous_receipts_only_accept_one_job(client, monkeypatch):
    await sign_in(client)
    release = asyncio.Event()
    async def generate(**kwargs):
        await release.wait()
        return [imagine.GeneratedImage(imagine._MOCK_PNG, "image/png")]
    provider = AsyncMock(side_effect=generate)
    monkeypatch.setattr(api, "generate_images", provider)
    monkeypatch.setattr(api, "_accept_lock", asyncio.Lock())
    request = {"prompt": "cùng một lượt", "background": True, "request_id": uuid.uuid4().hex}
    try:
        first, second = await asyncio.gather(client.post("/api/imagine", json=request), client.post("/api/imagine", json=request))
        assert sorted([first.status_code, second.status_code]) == [200, 202]
        assert first.json()["job"]["id"] == second.json()["job"]["id"]
    finally:
        release.set()
        await wait_tasks()
    provider.assert_awaited_once()
    # Xóa ảnh vẫn giữ dấu nhận request; gửi lại không sinh thêm ảnh có tính phí.
    job = first.json()["job"]
    await client.delete(f"/api/imagine/{job['id']}")
    assert (await client.post("/api/imagine", json=request)).status_code == 410
    provider.assert_awaited_once()


async def test_background_timeout_and_restart_are_not_replayed(client, monkeypatch):
    owner = await sign_in(client)
    async def slow(**kwargs):
        await asyncio.sleep(1)
        return [imagine.GeneratedImage(imagine._MOCK_PNG, "image/png")]
    provider = AsyncMock(side_effect=slow)
    monkeypatch.setattr(api, "generate_images", provider)
    monkeypatch.setattr(api, "IMAGINE_TIMEOUT_SECONDS", .01)
    request = {"prompt": "chậm", "background": True, "request_id": uuid.uuid4().hex}
    job = (await client.post("/api/imagine", json=request)).json()["job"]
    await wait_tasks()
    assert (await client.get(f"/api/imagine/{job['id']}")).json()["job"]["status"] == "unknown"
    await client.post("/api/imagine", json=request)
    provider.assert_awaited_once()
    orphan = await db.create_imagine_job(owner=owner, prompt="đang chạy", quality="low", resolution="1k", aspect_ratio="auto", status="queued")
    await db.interrupt_imagine_jobs()
    assert (await db.get_imagine_job(owner, orphan))["status"] == "unknown"
    provider.assert_awaited_once()


async def test_background_save_failure_cleans_outputs(client, monkeypatch):
    await sign_in(client)
    original = db.add_imagine_image
    calls = 0
    async def fail_second(**kwargs):
        nonlocal calls
        if kwargs["kind"] == "output":
            calls += 1
            if calls == 2: raise OSError("ổ đĩa giả bị đầy")
        return await original(**kwargs)
    monkeypatch.setattr(db, "add_imagine_image", fail_second)
    request = {"prompt": "hai ảnh", "n": 2, "source_images": [upload()], "background": True, "request_id": uuid.uuid4().hex}
    job = (await client.post("/api/imagine", json=request)).json()["job"]
    await wait_tasks()
    result = (await client.get(f"/api/imagine/{job['id']}")).json()["job"]
    assert result["status"] == "unknown" and result["images"] == []
    assert (await client.get(result["source_image"]["url"])).status_code == 200


async def test_pagination_and_job_lookup_are_private(client):
    owner = await sign_in(client)
    ids = [await db.create_imagine_job(owner=owner, prompt=f"ảnh {index}", quality="low", resolution="1k", aspect_ratio="auto") for index in range(43)]
    first = (await client.get("/api/imagine")).json()["jobs"]
    second = (await client.get("/api/imagine", params={"before": first[-1]["id"]})).json()["jobs"]
    assert len(first) == 40 and len(second) == 3
    assert set(ids) == {row["id"] for row in first + second}
    await sign_in(client)
    assert (await client.get(f"/api/imagine/{ids[0]}")).status_code == 404
    assert (await client.get("/api/imagine", params={"before": ids[0]})).json()["jobs"] == []
