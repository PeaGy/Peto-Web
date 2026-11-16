"""Companion bản AIRI dưới /companion/ khi PETO_AIRI_DIR được đặt; không đặt thì /companion vẫn là Companion React."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core import airi_static, config, static_files

AIRI_INDEX = "<!doctype html><html><head><title>AIRI</title></head><body><div id=app></div></body></html>"
SITE_INDEX = "<!doctype html><html><head><title>Peto</title></head><body></body></html>"
SITE_404 = "<!doctype html><title>Không tìm thấy</title>"
# Đường dẫn cũ của Companion React mà người dùng có thể đã lưu.
REACT_PATHS = ("/companion", "/companion/", "/companion/settings/", "/companion/settings/modules/voice",
               "/companion/settings/providers/openai", "/companion/settings/cards/peto/edit")


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
    (airi / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (tmp_path / "bi-mat.txt").write_text("TOKEN_THAT", encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(SITE_INDEX, encoding="utf-8")
    (site / "404.html").write_text(SITE_404, encoding="utf-8")
    return airi, site


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def airi_client(tmp_path, monkeypatch):
    airi, site = _build(tmp_path)
    monkeypatch.setattr(config, "AIRI_DIR", airi)
    app = FastAPI()
    assert airi_static.mount(app, airi)
    # Như main.py: trang chính bắt mọi đường dẫn còn lại, gắn sau cùng.
    assert static_files.mount(app, site)
    async with await _client(app) as client:
        yield client


async def test_index_and_redirect(airi_client):
    response = await airi_client.get("/companion")
    assert response.status_code == 308 and response.headers["location"] == "/companion/"
    response = await airi_client.head("/companion")
    assert response.status_code == 308
    response = await airi_client.get("/companion/")
    assert response.status_code == 200 and "<title>AIRI</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"


async def test_client_routes_get_index(airi_client):
    for path in ("/companion/settings", "/companion/settings/modules", "/companion/settings/modules/consciousness",
                 "/companion/chat/"):
        response = await airi_client.get(path)
        assert response.status_code == 200, path
        assert "<title>AIRI</title>" in response.text


async def test_old_react_deep_links_open_airi(airi_client):
    """Trang của Companion React không còn: AIRI nhận và tự hiện trang "Không tìm thấy" có lối về."""
    for path in REACT_PATHS[1:]:
        response = await airi_client.get(path)
        assert response.status_code == 200, path
        assert "<title>AIRI</title>" in response.text and "<title>Peto</title>" not in response.text


async def test_files_and_types(airi_client):
    response = await airi_client.get("/companion/assets/index-abc.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]
    response = await airi_client.get("/companion/assets/duckdb-xyz.wasm")
    assert response.headers["content-type"] == "application/wasm"
    response = await airi_client.get("/companion/manifest.webmanifest")
    assert response.headers["content-type"] == "application/manifest+json"
    response = await airi_client.head("/companion/favicon.svg")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-cache"


async def test_missing_asset_is_404_not_page(airi_client):
    for path in ("/companion/assets/missing-123.js", "/companion/sw-cu.js"):
        response = await airi_client.get(path)
        assert response.status_code == 404, path
        assert "AIRI" not in response.text and "Peto" not in response.text


async def test_path_traversal_blocked(airi_client):
    for path in ("/companion/../bi-mat.txt", "/companion/%2e%2e/bi-mat.txt", "/companion/..%2fbi-mat.txt",
                 "/companion/assets/..%2f..%2fbi-mat.txt", "/companion/%2e%2e%2fsite/index.html"):
        response = await airi_client.get(path)
        assert "TOKEN_THAT" not in response.text, path
        assert "<title>Peto</title>" not in response.text, path


async def test_peto_pages_unchanged(airi_client):
    for path in ("/", "/chat/abc", "/imagine"):
        response = await airi_client.get(path)
        assert response.status_code == 200 and "<title>Peto</title>" in response.text, path
    # /airi không còn là đường dẫn nào (chưa từng triển khai).
    response = await airi_client.get("/airi/")
    assert response.status_code == 404 and "AIRI" not in response.text


async def test_static_files_never_serves_react_companion_when_airi_is_on(tmp_path, monkeypatch):
    """Lớp phòng thủ thứ hai: dù route AIRI không có (bản build hỏng sau khi khởi động), trang chính không trả
    index.html của Companion React cho /companion… khi cờ đang bật."""
    airi, site = _build(tmp_path)
    monkeypatch.setattr(config, "AIRI_DIR", airi)
    app = FastAPI()
    assert static_files.mount(app, site)
    async with await _client(app) as client:
        for path in REACT_PATHS:
            response = await client.get(path)
            assert response.status_code == 404, path
            assert "<title>Peto</title>" not in response.text


async def test_disabled_without_dir(tmp_path, monkeypatch):
    """Không đặt PETO_AIRI_DIR (hay thư mục không có index.html): Companion React như cũ, /airi cũng không có."""
    _, site = _build(tmp_path)
    for airi_dir in (None, tmp_path / "khong-co"):
        monkeypatch.setattr(config, "AIRI_DIR", airi_dir)
        assert airi_static.active() is False
        app = FastAPI()
        assert airi_static.mount(app, airi_dir) is False
        static_files.mount(app, site)
        async with await _client(app) as client:
            for path in REACT_PATHS:
                response = await client.get(path)
                assert response.status_code == 200, path
                assert "<title>Peto</title>" in response.text and "AIRI" not in response.text
            for path in ("/companion/settings/khong-co-trang", "/companion/assets/index-abc.js", "/airi/"):
                response = await client.get(path)
                assert response.status_code == 404, path
                assert "AIRI" not in response.text


async def test_missing_index_after_startup_is_503_page(tmp_path, monkeypatch):
    """index.html biến mất sau khi khởi động (bản fork đang build lại): trang báo 503 tiếng Việt, không phải lỗi 500."""
    airi, site = _build(tmp_path)
    monkeypatch.setattr(config, "AIRI_DIR", airi)
    app = FastAPI()
    assert airi_static.mount(app, airi)
    assert static_files.mount(app, site)
    (airi / "index.html").unlink()
    async with await _client(app) as client:
        for path in ("/companion/", "/companion/settings/modules"):
            response = await client.get(path)
            assert response.status_code == 503, path
            assert "Companion đang cập nhật" in response.text and response.headers["retry-after"] == "30"
            assert response.headers["cache-control"] == "no-store"
        assert (await client.get("/companion/assets/index-abc.js")).status_code == 200


async def test_build_info_is_served_and_never_cached(airi_client, tmp_path):
    """peto-build.json (ghi bởi workflow của bản fork) cho biết bản nào đang chạy: luôn đọc mới, không cache."""
    (tmp_path / "airi" / "peto-build.json").write_text('{"commit": "abc"}', encoding="utf-8")
    response = await airi_client.get("/companion/peto-build.json")
    assert response.status_code == 200 and response.json() == {"commit": "abc"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")


def _symlink_or_skip(link, target):
    """Symlink thư mục; Windows không bật Developer Mode thì không tạo được: bỏ qua thay vì báo hỏng."""
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Hệ điều hành không cho tạo symlink: {error}")


def _switch(link, target):
    """Đổi symlink như deploy/update-companion.sh: tạo link tạm rồi thay link cũ trong một bước."""
    temp = link.with_name(link.name + ".moi")
    temp.symlink_to(target, target_is_directory=True)
    try:
        os.replace(temp, link)
    except PermissionError:
        # Windows không thay được symlink thư mục bằng một lần đổi tên (Linux thì được, như mv -T của script):
        # gỡ link cũ rồi đổi tên, chỉ trong bài kiểm tra.
        os.rmdir(link)
        os.replace(temp, link)


def _version(root, name: str, asset: str):
    folder = root / name
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(f"<!doctype html><title>AIRI {name}</title>", encoding="utf-8")
    (folder / "assets" / asset).write_text(f"console.log('{name}')", encoding="utf-8")
    (folder / "peto-build.json").write_text(f'{{"commit": "{name}"}}', encoding="utf-8")
    return folder


async def test_switched_symlink_is_followed_without_restart(tmp_path, monkeypatch):
    """PETO_AIRI_DIR là symlink current: đổi symlink là /companion/ đổi bản build ngay, không khởi động lại; tệp chỉ có
    ở bản cũ thì 404, và đường dẫn vòng sang bản cũ bị chặn như mọi path traversal."""
    _, site = _build(tmp_path)
    dist = tmp_path / "dist"
    _version(dist, "b1", "index-one.js")
    _version(dist, "b2", "index-two.js")
    current = dist / "current"
    _symlink_or_skip(current, dist / "b1")
    monkeypatch.setattr(config, "AIRI_DIR", current)
    app = FastAPI()
    assert airi_static.mount(app, current)
    assert static_files.mount(app, site)
    async with await _client(app) as client:
        assert "AIRI b1" in (await client.get("/companion/")).text
        assert (await client.get("/companion/peto-build.json")).json() == {"commit": "b1"}
        assert (await client.get("/companion/assets/index-one.js")).status_code == 200

        _switch(current, dist / "b2")
        assert "AIRI b2" in (await client.get("/companion/")).text
        assert "AIRI b2" in (await client.get("/companion/settings/modules")).text
        assert (await client.get("/companion/peto-build.json")).json() == {"commit": "b2"}
        assert (await client.get("/companion/assets/index-two.js")).status_code == 200
        assert (await client.get("/companion/assets/index-one.js")).status_code == 404
        for path in ("/companion/..%2fb1%2fassets%2findex-one.js", "/companion/%2e%2e/b1/peto-build.json",
                     "/companion/assets/..%2f..%2fb1%2fpeto-build.json", "/companion/..%2f..%2fbi-mat.txt"):
            response = await client.get(path)
            assert "b1" not in response.text and "TOKEN_THAT" not in response.text, path

        # Symlink trỏ vào thư mục không có index.html (hay đã bị xóa): trang 503 tạm thời, không lỗi 500.
        broken = dist / "dang-giai-nen"
        broken.mkdir()
        _switch(current, broken)
        response = await client.get("/companion/")
        assert response.status_code == 503 and "Companion đang cập nhật" in response.text
        assert airi_static.active() is False
        _switch(current, dist / "khong-con")
        assert (await client.get("/companion/settings")).status_code == 503

        _switch(current, dist / "b1")
        assert "AIRI b1" in (await client.get("/companion/")).text
        assert airi_static.active() is True


async def test_active_flag_follows_config(tmp_path, monkeypatch):
    airi, _ = _build(tmp_path)
    monkeypatch.setattr(config, "AIRI_DIR", airi)
    assert airi_static.active() is True
    (airi / "index.html").unlink()
    assert airi_static.active() is False
    monkeypatch.setattr(config, "AIRI_DIR", None)
    assert airi_static.active() is False


async def test_auth_me_reports_the_flag(anon_client, client, tmp_path, monkeypatch):
    """/api/auth/me mang đúng một cờ companion_airi, cho cả khách và người đã đăng nhập; không lộ đường dẫn."""
    airi, _ = _build(tmp_path)
    for value, expected in ((None, False), (airi, True)):
        monkeypatch.setattr(config, "AIRI_DIR", value)
        for web in (anon_client, client):
            body = (await web.get("/api/auth/me")).json()
            assert body["companion_airi"] is expected
            assert str(tmp_path) not in str(body) and "airi" not in str(body).replace("companion_airi", "")
