"""Tab Imagine: tạo ảnh tách khỏi chat, không gọi mạng khi dùng mock."""

from __future__ import annotations

from pathlib import Path

import auth
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
    monkeypatch.setattr(auth, "ALLOWED_DISCORD_IDS", auth.ALLOWED_DISCORD_IDS | {"222222222222222222"})
    client.cookies.set(SESSION_COOKIE, auth._sign(owner_key("222222222222222222")))
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
    text = body.decode("utf-8", errors="replace")
    assert "Imagine" in text
