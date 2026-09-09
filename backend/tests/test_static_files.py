"""Kiểm thử phần phục vụ frontend đã build."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import static_files


@pytest.fixture
def site(tmp_path):
    """Một bản build giả, đủ giống thứ Vite sinh ra."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<h1>Peto</h1>", encoding="utf-8")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.ico").write_text("x", encoding="utf-8")

    # File bí mật NGOÀI thư mục build, dùng để thử path traversal.
    (tmp_path.parent / "bi-mat.txt").write_text("TOKEN_THAT", encoding="utf-8")

    app = FastAPI()

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    assert static_files.mount(app, tmp_path)
    return app


@pytest.fixture
async def site_client(site):
    async with AsyncClient(
        transport=ASGITransport(app=site), base_url="http://test"
    ) as client:
        yield client


async def test_serves_index(site_client):
    response = await site_client.get("/")
    assert response.status_code == 200
    assert "Peto" in response.text


async def test_serves_hashed_asset_with_long_cache(site_client):
    response = await site_client.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


async def test_index_is_not_cached(site_client):
    response = await site_client.get("/")
    assert response.headers["cache-control"] == "no-cache"


async def test_unknown_path_falls_back_to_app(site_client):
    """Router phía client cần index.html cho đường dẫn lạ, không phải 404."""
    response = await site_client.get("/hoi-thoai/abc")
    assert response.status_code == 200
    assert "Peto" in response.text


async def test_api_routes_are_not_shadowed(site_client):
    assert (await site_client.get("/api/health")).json() == {"ok": True}


async def test_unknown_api_path_is_404_not_html(site_client):
    """API sai đường dẫn phải ra 404, không được trả về trang web."""
    response = await site_client.get("/api/khong-co-that")
    assert response.status_code == 404
    assert "Peto" not in response.text


@pytest.mark.parametrize(
    "attack",
    [
        "../bi-mat.txt",
        "..%2Fbi-mat.txt",
        "assets/../../bi-mat.txt",
        "....//bi-mat.txt",
    ],
)
async def test_path_traversal_cannot_escape_build_dir(site_client, attack):
    response = await site_client.get(f"/{attack}")
    assert "TOKEN_THAT" not in response.text


def test_mount_is_skipped_without_a_build(tmp_path):
    app = FastAPI()
    assert static_files.mount(app, tmp_path / "khong-ton-tai") is False


async def test_head_is_supported(site_client):
    """`curl -I` và công cụ giám sát uptime dùng HEAD.

    FastAPI không tự thêm HEAD cho route GET, nên phải khai báo rõ — thiếu là
    kiểm tra deploy bằng `curl -sI` sẽ ra 405 và làm người ta tưởng hỏng.
    """
    response = await site_client.head("/")
    assert response.status_code == 200


async def test_head_on_unknown_path_also_falls_back(site_client):
    assert (await site_client.head("/hoi-thoai/abc")).status_code == 200
