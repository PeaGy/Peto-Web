"""Tab Imagine: tạo ảnh tách khỏi chat, không gọi mạng khi dùng mock."""

from __future__ import annotations

from pathlib import Path

import auth
import asyncio
import base64
import json
import httpx
import pytest
from ai import imagine
from ai.base import ProviderError
import imagine_api
from config import SESSION_COOKIE, UPLOAD_DIR, owner_key


async def test_imagine_creates_and_serves_image(client):
    response = await client.post(
        "/api/imagine",
        json={
            "prompt": "một con mèo đội mũ",
            "quality": "low",
            "resolution": "1k",
            "aspect_ratio": "1:1",
            "n": 2,
        },
    )
    assert response.status_code == 200
    job = response.json()["job"]
    assert job["prompt"] == "một con mèo đội mũ"
    assert job["quality"] == "low"
    assert len(job["images"]) == 2

    listed = await client.get("/api/imagine")
    assert listed.status_code == 200
    jobs = listed.json()["jobs"]
    assert jobs[0]["id"] == job["id"]
    assert len(jobs[0]["images"]) == 2

    image_url = job["images"][0]["url"]
    fetched = await client.get(image_url)
    assert fetched.status_code == 200
    assert fetched.content.startswith(b"\x89PNG")
    download = await client.get(image_url + "?download=1")
    assert "attachment" in download.headers["content-disposition"]
    assert "peto-" in download.headers["content-disposition"]


async def test_imagine_rejects_empty_and_bad_options(client):
    assert (await client.post("/api/imagine", json={"prompt": "   "})).status_code == 400
    assert (
        await client.post(
            "/api/imagine", json={"prompt": "mèo", "quality": "ultra"}
        )
    ).status_code == 400
    assert (
        await client.post(
            "/api/imagine", json={"prompt": "mèo", "aspect_ratio": "99:1"}
        )
    ).status_code == 400


async def test_imagine_error_keyword(client):
    response = await client.post(
        "/api/imagine", json={"prompt": "__error__ bức này"}
    )
    assert response.status_code == 502


async def test_imagine_image_hidden_from_other_user(client, monkeypatch):
    created = await client.post(
        "/api/imagine", json={"prompt": "bí mật", "n": 1}
    )
    url = created.json()["job"]["images"][0]["url"]
    client.cookies.set(SESSION_COOKIE, auth._sign(owner_key("discord", "222222222222222222")))
    assert (await client.get(url)).status_code == 404


async def test_delete_imagine_job_removes_files(client):
    created = await client.post(
        "/api/imagine", json={"prompt": "xóa tôi đi", "n": 1}
    )
    job = created.json()["job"]
    folder = Path(UPLOAD_DIR) / "imagine" / job["id"]
    assert folder.exists()
    deleted = await client.delete(f"/api/imagine/{job['id']}")
    assert deleted.status_code == 200
    assert (await client.delete(f"/api/imagine/{job['id']}")).status_code == 404
    assert not folder.exists()


async def test_chat_does_not_create_imagine_job(client):
    """Nhờ vẽ trong chat phải ở lại chat, không lén gọi Imagine."""
    before = len((await client.get("/api/imagine")).json()["jobs"])
    async with client.stream("POST", "/api/chat", json={"message": "vẽ giúp con mèo"}) as response:
        assert response.status_code == 200
        body = b""
        async for chunk in response.aiter_bytes():
            body += chunk
    after = (await client.get("/api/imagine")).json()["jobs"]
    assert len(after) == before
    events = [json.loads(line[6:]) for line in body.decode("utf-8").splitlines() if line.startswith("data: ")]
    text = "".join(event["text"] for event in events if event["type"] == "delta")
    assert "Tạo ảnh" in text


async def test_image_prompt_keeps_line_breaks(client):
    prompt = "  Bố cục:\n  - mèo trắng\n  - nền tím  "
    created = await client.post("/api/imagine", json={"prompt": prompt})
    assert created.json()["job"]["prompt"] == prompt.strip()


async def test_image_timeout_releases_slot_and_does_not_save_job(client, monkeypatch):
    original = imagine_api.generate_images
    before = (await client.get("/api/imagine")).json()["jobs"]

    async def slow(**kwargs):
        await asyncio.sleep(1)
        return await original(**kwargs)

    monkeypatch.setattr(imagine_api, "generate_images", slow)
    monkeypatch.setattr(imagine_api, "IMAGINE_TIMEOUT_SECONDS", 0.01)
    response = await client.post("/api/imagine", json={"prompt": "mèo"})
    assert response.status_code == 504
    assert (await client.get("/api/imagine")).json()["jobs"] == before
    monkeypatch.setattr(imagine_api, "generate_images", original)
    assert (await client.post("/api/imagine", json={"prompt": "thử lại"})).status_code == 200


async def test_other_owner_cannot_list_or_delete_images(client, monkeypatch):
    created = await client.post("/api/imagine", json={"prompt": "riêng tư"})
    job_id = created.json()["job"]["id"]
    client.cookies.set(SESSION_COOKIE, auth._sign(owner_key("discord", "222222222222222222")))
    assert (await client.get("/api/imagine")).json()["jobs"] == []
    assert (await client.delete(f"/api/imagine/{job_id}")).status_code == 404


@pytest.mark.parametrize("item", [
    {"b64_json": "not base64"},
    {"b64_json": base64.b64encode(b"<html>bad gateway</html>").decode(), "mime_type": "image/png"},
    {"b64_json": 123},
])
def test_invalid_image_bytes_are_not_published(item):
    assert imagine._decode_payload(item) is None


def mock_image_service(monkeypatch, handler):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(imagine, "AI_PROVIDER", "xai")
    monkeypatch.setattr(imagine.httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    async def token(self):
        return "fake-test-token"

    monkeypatch.setattr(imagine.XaiAuth, "get_access_token", token)


async def test_image_provider_keeps_real_model_id_and_request_options(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(imagine._MOCK_PNG).decode()}]})

    mock_image_service(monkeypatch, handler)
    result = await imagine.generate_images(prompt="mèo", quality="medium", resolution="2k", aspect_ratio="16:9", n=1)
    payload = json.loads(requests[0].content)
    assert payload == {"model": imagine.IMAGINE_MODEL, "prompt": "mèo", "quality": "medium", "resolution": "2k", "aspect_ratio": "16:9", "n": 1, "response_format": "b64_json"}
    assert requests[0].url.path.endswith("/images/generations")
    assert result[0].mime == "image/png"


@pytest.mark.parametrize("body", [[], None, {"data": "wrong"}, {"data": [None, "bad"]}])
async def test_malformed_provider_response_is_readable_error(monkeypatch, body):
    mock_image_service(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(ProviderError, match="Peto"):
        await imagine.generate_images(prompt="mèo", quality="low", resolution="1k", aspect_ratio="auto", n=1)


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
async def test_provider_errors_use_peto_and_hide_raw_response(monkeypatch, status):
    mock_image_service(monkeypatch, lambda request: httpx.Response(status, text="Grok xAI internal secret"))
    with pytest.raises(ProviderError) as caught:
        await imagine.generate_images(prompt="mèo", quality="low", resolution="1k", aspect_ratio="auto", n=1)
    message = str(caught.value)
    assert not any(word in message for word in ("Grok", "xAI", "secret"))
