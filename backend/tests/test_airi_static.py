"""Phục vụ bản build AIRI dưới /airi/ khi PETO_AIRI_DIR được đặt; không đặt thì không có route nào."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core import airi_static, static_files

AIRI_INDEX = "<!doctype html><html><head><title>AIRI</title></head><body><div id=app></div></body></html>"
SITE_INDEX = "<!doctype html><html><head><title>Peto</title></head><body></body></html>"


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    async def fake_identity() -> dict:
        return {"name": "Peto", "avatar_url": None}

    monkeypatch.setattr(static_files, "get_app_identity", fake_identity)


def _build(tmp_path):
    airi = tmp_path / "airi"
    (airi / "assets").mkdir(parents=True)
    (airi / "index.html").write_text(AIRI_INDEX, encoding="utf-8")
    (airi / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    (airi / "assets" / "duckdb-xyz.wasm").write_bytes(b"\0asm")
    (airi / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "bi-mat.txt").write_text("TOKEN_THAT", encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(SITE_INDEX, encoding="utf-8")
    return airi, site


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def airi_client(tmp_path):
    airi, site = _build(tmp_path)
    app = FastAPI()
    assert airi_static.mount(app, airi)
    # Như main.py: trang chính bắt mọi đường dẫn còn lại, gắn sau cùng.
    assert static_files.mount(app, site)
    async with await _client(app) as client:
        yield client


async def test_index_and_redirect(airi_client):
    response = await airi_client.get("/airi")
    assert response.status_code == 308 and response.headers["location"] == "/airi/"
    response = await airi_client.get("/airi/")
    assert response.status_code == 200 and "<title>AIRI</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"


async def test_client_routes_get_index(airi_client):
    for path in ("/airi/settings", "/airi/settings/modules/consciousness", "/airi/chat/"):
        response = await airi_client.get(path)
        assert response.status_code == 200, path
        assert "<title>AIRI</title>" in response.text


async def test_files_and_types(airi_client):
    response = await airi_client.get("/airi/assets/index-abc.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]
    response = await airi_client.get("/airi/assets/duckdb-xyz.wasm")
    assert response.headers["content-type"] == "application/wasm"
    response = await airi_client.head("/airi/favicon.svg")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-cache"


async def test_missing_asset_is_404_not_page(airi_client):
    response = await airi_client.get("/airi/assets/missing-123.js")
    assert response.status_code == 404
    assert "AIRI" not in response.text


async def test_path_traversal_blocked(airi_client):
    for path in ("/airi/../bi-mat.txt", "/airi/%2e%2e/bi-mat.txt", "/airi/..%2fbi-mat.txt"):
        response = await airi_client.get(path)
        assert "TOKEN_THAT" not in response.text, path


async def test_peto_pages_unchanged(airi_client):
    response = await airi_client.get("/")
    assert "<title>Peto</title>" in response.text
    response = await airi_client.get("/companion")
    assert "<title>Peto</title>" in response.text


async def test_disabled_without_dir(tmp_path):
    _, site = _build(tmp_path)
    app = FastAPI()
    assert airi_static.mount(app, None) is False
    assert airi_static.mount(app, tmp_path / "khong-co") is False
    static_files.mount(app, site)
    async with await _client(app) as client:
        response = await client.get("/airi/")
        assert response.status_code == 404
        assert "AIRI" not in response.text
