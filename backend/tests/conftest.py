"""Cấu hình test — chạy hoàn toàn bằng dữ liệu giả.

Đặt biến môi trường TRƯỚC khi bất kỳ module nào import ``config``, để test
không bao giờ chạm vào database, token hay tài khoản thật.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="peto_web_test_"))
os.environ["PETO_WEB_DB"] = str(_TMP_DIR / "test.db")
os.environ["PETO_XAI_TOKEN_PATH"] = str(_TMP_DIR / "xai_tokens.json")
os.environ["PETO_AI_PROVIDER"] = "mock"
os.environ["PETO_COOLDOWN_SECONDS"] = "0"
# Không để credential thật của máy lọt vào test.
os.environ.pop("XAI_API_KEY", None)

# Thông tin Discord giả — đủ để bật luồng đăng nhập, không gọi ra ngoài.
os.environ["DISCORD_CLIENT_ID"] = "test-client-id"
os.environ["DISCORD_CLIENT_SECRET"] = "test-client-secret"
os.environ["PETO_SESSION_SECRET"] = "test-session-secret"
TEST_DISCORD_ID = "111111111111111111"
BLOCKED_DISCORD_ID = "999999999999999999"
os.environ["PETO_ALLOWED_DISCORD_IDS"] = TEST_DISCORD_ID

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import auth  # noqa: E402
import db  # noqa: E402
from config import SESSION_COOKIE, owner_key  # noqa: E402
from main import app  # noqa: E402

TEST_OWNER = owner_key(TEST_DISCORD_ID)


def _make_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture
async def anon_client() -> AsyncClient:
    """Client chưa đăng nhập."""
    await db.init_db()
    async with _make_client() as client:
        yield client


@pytest.fixture
async def client() -> AsyncClient:
    """Client đã đăng nhập bằng một danh tính Discord giả."""
    await db.init_db()
    await db.upsert_user(
        owner=TEST_OWNER,
        discord_id=TEST_DISCORD_ID,
        username="nguoi_test",
        display_name="Người Test",
        avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
    )
    async with _make_client() as async_client:
        async_client.cookies.set(SESSION_COOKIE, auth._sign(TEST_OWNER))
        yield async_client


async def read_events(response) -> list[dict]:
    """Gom các sự kiện SSE từ một response đang stream."""
    import json

    events: list[dict] = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events
